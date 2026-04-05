"""Base class and shared types for billing providers."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests


@dataclass
class UsageRecord:
    provider: str
    model: str
    month: str            # YYYY-MM
    input_tokens: int
    output_tokens: int
    cost: Optional[float] = None       # None → computed via pricing; float → pre-computed (e.g. Google)
    extra: dict = field(default_factory=dict)  # provider-specific token buckets for cost calc


class BillingProvider(ABC):
    name: str  # set as class attribute on each subclass

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Return (ok, reason). reason is empty string when ok."""

    @abstractmethod
    def fetch(self, start: datetime, end: datetime) -> list[UsageRecord]:
        """Fetch usage records for the date range."""


# ── Shared HTTP helper ────────────────────────────────────────────────────────

def api_get(url: str, headers: dict, max_retries: int = 5) -> Optional[dict]:
    """GET with exponential backoff. Returns parsed JSON or None on failure."""
    backoff = 2
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                time.sleep(backoff)
                backoff *= 2
                continue
            return None
        except requests.RequestException:
            if attempt < max_retries - 1:
                time.sleep(backoff)
                backoff *= 2
    return None
