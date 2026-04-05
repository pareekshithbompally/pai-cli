"""Provider registry."""

from __future__ import annotations

from .anthropic import AnthropicProvider
from .base import BillingProvider, UsageRecord
from .google import GoogleProvider
from .openai import OpenAIProvider

_PROVIDERS: dict[str, BillingProvider] = {
    p.name: p
    for p in [OpenAIProvider(), AnthropicProvider(), GoogleProvider()]
}

ALL_PROVIDERS: list[str] = list(_PROVIDERS.keys())


def get_provider(name: str) -> BillingProvider:
    if name not in _PROVIDERS:
        raise KeyError(f"Unknown provider: {name!r}. Available: {ALL_PROVIDERS}")
    return _PROVIDERS[name]


def get_providers(names: list[str]) -> list[BillingProvider]:
    return [get_provider(n) for n in names]
