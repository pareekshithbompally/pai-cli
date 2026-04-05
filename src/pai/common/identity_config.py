"""Shared identity setup/config path helpers."""

from __future__ import annotations

import json
from pathlib import Path

from .paths import app_config_path, app_data_path


def identity_config_dir() -> Path:
    return app_config_path("identity")


def identity_data_dir() -> Path:
    return app_data_path("identity")


def identity_agent_config_path(agent: str) -> Path:
    return app_config_path("identity", "agents", f"{agent}.json")


def identity_collector_config_path(agent: str) -> Path:
    return app_config_path("identity", f"{agent}-collector.yaml")


def identity_raw_path(agent: str) -> Path:
    suffix = "telemetry.jsonl" if agent == "gemini" else "otel.jsonl"
    return app_data_path("identity", "raw", f"{agent}-{suffix}")


def legacy_identity_raw_paths(agent: str) -> tuple[Path, ...]:
    if agent == "claude":
        return (Path.home() / ".claude" / "custom-user-work" / "claude-otel-raw.jsonl",)
    return ()


def legacy_identity_session_map_path(agent: str) -> Path | None:
    if agent == "claude":
        return Path.home() / ".claude" / "custom-user-work" / "session-accounts.jsonl"
    return None


def load_identity_agent_config(agent: str) -> dict[str, str]:
    path = identity_agent_config_path(agent)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
