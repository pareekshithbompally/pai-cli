"""Declarative storage metadata for supported agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ..common.paths import hidden_tool_dir


@dataclass(frozen=True)
class AgentLocation:
    name: str
    root_dir: Path
    session_globs: tuple[str, ...]
    plan_globs: tuple[str, ...] = ()
    files: Mapping[str, Path] = field(default_factory=dict)

    def session_files(self) -> list[Path]:
        return _glob_files(self.root_dir, self.session_globs)

    def plan_files(self) -> list[Path]:
        return _glob_files(self.root_dir, self.plan_globs)


def _glob_files(root_dir: Path, patterns: tuple[str, ...]) -> list[Path]:
    if not root_dir.exists():
        return []

    files: list[Path] = []
    for pattern in patterns:
        files.extend(path for path in root_dir.glob(pattern) if path.is_file())
    return files


def _build_locations() -> dict[str, AgentLocation]:
    claude_root = hidden_tool_dir("claude")
    codex_root = hidden_tool_dir("codex")
    copilot_root = hidden_tool_dir("copilot")
    gemini_root = hidden_tool_dir("gemini")
    vibe_root = hidden_tool_dir("vibe")

    return {
        "claude": AgentLocation(
            name="claude",
            root_dir=claude_root,
            session_globs=("projects/*/*.jsonl",),
            plan_globs=("plans/*.md",),
        ),
        "codex": AgentLocation(
            name="codex",
            root_dir=codex_root,
            session_globs=("sessions/*/*/*/rollout-*.jsonl",),
            plan_globs=("plans/*/*.md",),
            files={
                "session_index": codex_root / "session_index.jsonl",
            },
        ),
        "copilot": AgentLocation(
            name="copilot",
            root_dir=copilot_root,
            session_globs=("session-state/*/events.jsonl", "session-state/*.jsonl"),
            plan_globs=("session-state/*/plan.md",),
        ),
        "gemini": AgentLocation(
            name="gemini",
            root_dir=gemini_root,
            session_globs=("tmp/*/chats/session-*.json",),
        ),
        "vibe": AgentLocation(
            name="vibe",
            root_dir=vibe_root,
            session_globs=("logs/session/*/messages.jsonl",),
        ),
    }


_AGENT_LOCATIONS = _build_locations()


def get_agent_location(name: str) -> AgentLocation:
    return _AGENT_LOCATIONS[name]


def iter_agent_locations() -> list[AgentLocation]:
    return list(_AGENT_LOCATIONS.values())
