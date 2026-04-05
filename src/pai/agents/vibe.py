"""Vibe CLI agent adapter.

Sessions  : ~/.vibe/logs/session/<session_dir>/messages.jsonl
Metadata  : ~/.vibe/logs/session/<session_dir>/meta.json
Plans     : none
Tokens    : meta.stats.{session_prompt_tokens,context_tokens,session_completion_tokens}
Identity  : provider from ~/.vibe/config.toml when available
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional
import tomllib

from ..common.accounts import provider_identity, unknown_identity
from ..common.types import MessageRecord, PlanRecord, SessionRecord
from .base import AgentAdapter
from .catalog import get_agent_location

_LOCATION = get_agent_location("vibe")
CONFIG_FILE = _LOCATION.root_dir / "config.toml"


class VibeAdapter(AgentAdapter):
    name = "vibe"

    def discover_files(self) -> list[Path]:
        return _LOCATION.session_files()

    def parse_session(self, path: Path) -> Optional[SessionRecord]:
        meta = _read_meta(path)
        session_id = _session_id(path, meta)
        project = _project_name(meta)
        identity = _read_vibe_identity(CONFIG_FILE)

        msg_count = 0
        try:
            with path.open(encoding="utf-8") as f:
                for line in f:
                    data = _parse_line(line)
                    if data is None:
                        continue
                    if data.get("role") == "user" and str(data.get("content", "")).strip():
                        msg_count += 1
        except OSError:
            return None

        if msg_count == 0:
            return None

        stats = meta.get("stats", {}) if isinstance(meta, dict) else {}
        in_tokens = (stats.get("session_prompt_tokens") or 0) + (stats.get("context_tokens") or 0)
        out_tokens = stats.get("session_completion_tokens") or 0

        return SessionRecord(
            agent=self.name,
            file_path=str(path),
            session_id=session_id,
            project=project,
            msg_count=msg_count,
            first_ts=meta.get("start_time") if isinstance(meta, dict) else None,
            last_ts=meta.get("end_time") if isinstance(meta, dict) else None,
            in_tokens=in_tokens,
            out_tokens=out_tokens,
            identity_value=identity.value,
            identity_kind=identity.kind,
            identity_source=identity.source,
            identity_label=identity.label,
        )

    def iter_messages(self, path: Path) -> Iterator[MessageRecord]:
        try:
            with path.open(encoding="utf-8") as f:
                for line in f:
                    data = _parse_line(line)
                    if data is None or data.get("role") != "user":
                        continue
                    text = str(data.get("content", "")).strip()
                    if text:
                        yield MessageRecord(timestamp="", text=text)
        except OSError:
            return

    def iter_plans(self) -> Iterator[PlanRecord]:
        return iter([])


def _parse_line(line: str) -> Optional[dict]:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _read_meta(messages_path: Path) -> dict:
    meta_path = messages_path.with_name("meta.json")
    if not meta_path.exists():
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _session_id(messages_path: Path, meta: dict) -> str:
    session_id = meta.get("session_id")
    if isinstance(session_id, str) and session_id:
        return session_id

    dir_name = messages_path.parent.name
    if dir_name.startswith("session_"):
        return dir_name.split("_")[-1]
    return dir_name


def _project_name(meta: dict) -> str:
    env = meta.get("environment", {}) if isinstance(meta, dict) else {}
    cwd = env.get("working_directory", "") if isinstance(env, dict) else ""
    if cwd:
        return _abbreviate_path(cwd)
    title = meta.get("title", "") if isinstance(meta, dict) else ""
    return title or "—"


def _abbreviate_path(path: str) -> str:
    import os

    path = path.replace(os.path.expanduser("~"), "~")
    if len(path) > 36:
        path = path[:10] + "…" + path[-24:]
    return path


def _read_vibe_identity(config_path: Path):
    if not config_path.exists():
        return unknown_identity("vibe-none")
    try:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return unknown_identity("vibe-none")

    if not isinstance(data, dict):
        return unknown_identity("vibe-none")

    for key in ("provider", "model"):
        section = data.get(key)
        if not isinstance(section, dict):
            continue
        provider = section.get("provider")
        if isinstance(provider, str) and provider.strip():
            return provider_identity(provider, "vibe-config")

    return unknown_identity("vibe-none")
