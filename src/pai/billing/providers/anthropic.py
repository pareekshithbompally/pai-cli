"""Anthropic billing provider.

Reads ANTHROPIC_ADMIN_API_KEY from environment.
Fetches message usage via the Anthropic organization usage report API.
Tracks ephemeral cache writes (5m and 1h TTL) and cache reads separately.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

from .base import BillingProvider, UsageRecord, api_get

_API_VERSION = "2023-06-01"


class AnthropicProvider(BillingProvider):
    name = "anthropic"

    def is_available(self) -> tuple[bool, str]:
        if not os.environ.get("ANTHROPIC_ADMIN_API_KEY"):
            return False, "ANTHROPIC_ADMIN_API_KEY not set"
        return True, ""

    def fetch(self, start: datetime, end: datetime) -> list[UsageRecord]:
        key = os.environ.get("ANTHROPIC_ADMIN_API_KEY", "")
        headers = {
            "x-api-key": key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }

        start_rfc = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_rfc   = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        all_buckets: list[dict] = []
        next_page = None
        has_more = True

        while has_more:
            url = (
                f"https://api.anthropic.com/v1/organizations/usage_report/messages"
                f"?starting_at={start_rfc}&ending_at={end_rfc}"
                "&bucket_width=1d&limit=31&group_by[]=model"
            )
            if next_page:
                url += f"&page={next_page}"

            resp = api_get(url, headers)
            if not resp:
                break

            all_buckets.extend(resp.get("data", []))
            has_more = resp.get("has_more", False)
            next_page = resp.get("next_page")
            if not has_more or not next_page:
                break
            time.sleep(0.5)

        aggregated: dict[tuple[str, str], dict] = {}

        for bucket in all_buckets:
            starting_at = bucket.get("starting_at", "")
            month = starting_at[:7] if len(starting_at) >= 7 else "unknown"

            for result in bucket.get("results", []):
                model = result.get("model") or "unknown"
                key_ = (model, month)
                if key_ not in aggregated:
                    aggregated[key_] = {
                        "input_tokens":   0,
                        "output_tokens":  0,
                        "cache_write_5m": 0,
                        "cache_write_1h": 0,
                        "cache_read":     0,
                    }
                aggregated[key_]["input_tokens"]   += result.get("uncached_input_tokens", 0)
                aggregated[key_]["output_tokens"]  += result.get("output_tokens", 0)
                aggregated[key_]["cache_read"]     += result.get("cache_read_input_tokens", 0)

                cc = result.get("cache_creation") or {}
                aggregated[key_]["cache_write_5m"] += cc.get("ephemeral_5m_input_tokens", 0)
                aggregated[key_]["cache_write_1h"] += cc.get("ephemeral_1h_input_tokens", 0)

        return [
            UsageRecord(
                provider="Anthropic",
                model=model,
                month=month,
                input_tokens=v["input_tokens"],
                output_tokens=v["output_tokens"],
                cost=None,
                extra={
                    "cache_write_5m": v["cache_write_5m"],
                    "cache_write_1h": v["cache_write_1h"],
                    "cache_read":     v["cache_read"],
                },
            )
            for (model, month), v in aggregated.items()
        ]
