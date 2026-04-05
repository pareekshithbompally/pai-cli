"""OpenAI billing provider.

Reads OPENAI_ADMIN_API_KEY from environment.
Fetches completions usage via the OpenAI organization usage API, grouped by model.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

from .base import BillingProvider, UsageRecord, api_get


class OpenAIProvider(BillingProvider):
    name = "openai"

    def is_available(self) -> tuple[bool, str]:
        if not os.environ.get("OPENAI_ADMIN_API_KEY"):
            return False, "OPENAI_ADMIN_API_KEY not set"
        return True, ""

    def fetch(self, start: datetime, end: datetime) -> list[UsageRecord]:
        key = os.environ.get("OPENAI_ADMIN_API_KEY", "")
        headers = {"Authorization": f"Bearer {key}"}
        aggregated: dict[tuple[str, str], dict] = {}

        current = start
        while current < end:
            chunk_end = min(current + timedelta(days=31), end)
            url = (
                "https://api.openai.com/v1/organization/usage/completions"
                f"?start_time={int(current.timestamp())}"
                f"&end_time={int(chunk_end.timestamp())}"
                "&bucket_width=1d&limit=31&group_by=model"
            )
            resp = api_get(url, headers)
            if resp:
                for bucket in resp.get("data", []):
                    ts = bucket.get("start_time")
                    if not ts:
                        continue
                    month = datetime.fromtimestamp(ts).strftime("%Y-%m")
                    for result in bucket.get("results", []):
                        model = result.get("model") or "unknown"
                        key_ = (model, month)
                        if key_ not in aggregated:
                            aggregated[key_] = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
                        aggregated[key_]["input_tokens"]  += result.get("input_tokens", 0)
                        aggregated[key_]["output_tokens"] += result.get("output_tokens", 0)
                        aggregated[key_]["cached_tokens"] += result.get("input_cached_tokens", 0)
            current = chunk_end
            time.sleep(0.5)

        return [
            UsageRecord(
                provider="OpenAI",
                model=model,
                month=month,
                input_tokens=v["input_tokens"],
                output_tokens=v["output_tokens"],
                cost=None,
                extra={"cached_tokens": v["cached_tokens"]},
            )
            for (model, month), v in aggregated.items()
        ]
