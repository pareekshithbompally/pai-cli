"""LiteLLM pricing cache.

Fetches per-token pricing from the LiteLLM public repository, transforms it
to per-1M-token rates, and caches locally at XDG_CACHE_HOME/pai/api_pricing.json.

compute_cost(record) is the single public function for cost calculation.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import requests

from ..common.paths import app_cache_path
from .providers.base import UsageRecord

LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)

_CACHE_FILE = app_cache_path("api_pricing.json")
_CACHE_DIR = _CACHE_FILE.parent


# ── Fetch & transform ─────────────────────────────────────────────────────────

def _fetch_raw() -> dict:
    try:
        resp = requests.get(LITELLM_PRICING_URL, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def _transform(raw: dict) -> tuple[dict, dict]:
    """Return (openai_pricing, anthropic_pricing), rates per 1M tokens."""
    openai: dict    = {}
    anthropic: dict = {}

    for model, details in raw.items():
        per_m = 1_000_000
        inp   = (details.get("input_cost_per_token")  or 0) * per_m
        out   = (details.get("output_cost_per_token") or 0) * per_m
        cr    = (details.get("cache_read_input_token_cost")       or 0) * per_m
        cw    = (details.get("cache_creation_input_token_cost")   or 0) * per_m

        provider = (details.get("litellm_provider") or "").lower()

        if provider == "openai" or "gpt" in model:
            entry: dict = {"input": inp, "output": out}
            if cr > 0:
                entry["cached"] = cr
            openai[model] = entry

        elif provider == "anthropic" or "claude" in model:
            anthropic[model] = {
                "input":          inp,
                "output":         out,
                "cache_read":     cr,
                "cache_write_5m": cw,
                "cache_write_1h": cw * 1.25 if cw > 0 else 0,
            }

    return openai, anthropic


# ── Cache I/O ─────────────────────────────────────────────────────────────────

def load_pricing() -> dict:
    """Load from cache file. Fetches fresh if cache is missing."""
    if _CACHE_FILE.exists():
        try:
            with _CACHE_FILE.open() as f:
                return json.load(f)
        except Exception:
            pass
    return refresh_pricing()


def refresh_pricing() -> dict:
    """Fetch latest from LiteLLM and write to cache. Returns the cache dict."""
    raw = _fetch_raw()
    if not raw:
        return {"openai": {}, "anthropic": {}, "last_updated": None}

    openai, anthropic = _transform(raw)
    cache = {
        "openai":       openai,
        "anthropic":    anthropic,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with _CACHE_FILE.open("w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass
    return cache


def pricing_cache_path() -> Path:
    return _CACHE_FILE


def pricing_last_updated(cache: dict) -> str:
    return cache.get("last_updated") or "never"


# ── Cost calculation ──────────────────────────────────────────────────────────

def _lookup(pricing_table: dict, model: str) -> Optional[dict]:
    """Exact match first, then longest prefix match."""
    if model in pricing_table:
        return pricing_table[model]
    best, best_len = None, 0
    for key in pricing_table:
        if model.startswith(key) and len(key) > best_len:
            best, best_len = key, len(key)
    return pricing_table.get(best) if best else None


def compute_cost(record: UsageRecord, pricing: dict) -> float:
    """Return cost in USD for a UsageRecord. Returns 0.0 if no pricing found."""
    if record.cost is not None:
        return record.cost  # pre-computed (e.g. Google)

    provider_key = record.provider.lower()
    table = pricing.get(provider_key, {})
    rates = _lookup(table, record.model)
    if not rates:
        return 0.0

    cost  = (record.input_tokens  * rates.get("input",  0)) / 1_000_000
    cost += (record.output_tokens * rates.get("output", 0)) / 1_000_000

    if provider_key == "openai":
        cost += (record.extra.get("cached_tokens", 0) * rates.get("cached", 0)) / 1_000_000
    elif provider_key == "anthropic":
        cost += (record.extra.get("cache_write_5m", 0) * rates.get("cache_write_5m", 0)) / 1_000_000
        cost += (record.extra.get("cache_write_1h", 0) * rates.get("cache_write_1h", 0)) / 1_000_000
        cost += (record.extra.get("cache_read",     0) * rates.get("cache_read",     0)) / 1_000_000

    return cost
