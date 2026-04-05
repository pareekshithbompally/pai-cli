"""Agent registry — maps agent name to adapter instance."""

from __future__ import annotations

from .base import AgentAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .copilot import CopilotAdapter
from .gemini import GeminiAdapter
from .vibe import VibeAdapter

_ADAPTERS: dict[str, AgentAdapter] = {
    "claude":  ClaudeAdapter(),
    "codex":   CodexAdapter(),
    "copilot": CopilotAdapter(),
    "gemini":  GeminiAdapter(),
    "vibe":    VibeAdapter(),
}

ALL_AGENTS = list(_ADAPTERS.keys())


def get_adapter(name: str) -> AgentAdapter:
    if name not in _ADAPTERS:
        raise KeyError(f"Unknown agent: {name!r}. Available: {ALL_AGENTS}")
    return _ADAPTERS[name]


def get_adapters(names: list[str]) -> list[AgentAdapter]:
    return [get_adapter(n) for n in names]
