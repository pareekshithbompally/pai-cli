"""Google Gemini CLI agent adapter.

Sessions  : ~/.gemini/tmp/<project>/chats/session-*.json
Logs      : ~/.gemini/tmp/<project>/logs.json  (flat message log, secondary)
Tokens    : per gemini-response message → tokens.{input, output, cached, thoughts}
Identity  : auth mode from ~/.gemini/settings.json when available

Session file structure:
{
  "sessionId": "...",
  "startTime": "...",
  "lastUpdated": "...",
  "summary": "...",
  "messages": [
    {"id": "...", "timestamp": "...", "type": "user",   "content": [{"text": "..."}]},
    {"id": "...", "timestamp": "...", "type": "gemini", "content": "...", "tokens": {...}}
  ]
}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

from ..common.accounts import auth_mode_identity, unknown_identity
from ..common.types import MessageRecord, PlanRecord, SessionRecord
from .base import AgentAdapter
from .catalog import get_agent_location

_LOCATION = get_agent_location("gemini")


class GeminiAdapter(AgentAdapter):
    name = "gemini"

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover_files(self) -> list[Path]:
        return _LOCATION.session_files()

    # ── Parsing ───────────────────────────────────────────────────────────────

    def parse_session(self, path: Path) -> Optional[SessionRecord]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        session_id = data.get("sessionId", path.stem)
        project    = path.parent.parent.name  # ~/.gemini/tmp/<project>/chats/
        summary    = data.get("summary", "")
        messages   = data.get("messages", [])

        if not isinstance(messages, list):
            return None

        msg_count = 0
        first_ts = last_ts = None
        in_tokens = out_tokens = 0

        for msg in messages:
            if not isinstance(msg, dict):
                continue

            ts = msg.get("timestamp")
            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

            msg_type = msg.get("type", "")

            if msg_type == "user":
                text = _extract_user_text(msg)
                if text:
                    msg_count += 1

            elif msg_type == "gemini":
                tokens = msg.get("tokens")
                if isinstance(tokens, dict):
                    # input + cached for total context consumed
                    in_tokens  += (tokens.get("input") or 0) + (tokens.get("cached") or 0)
                    # output + thoughts (model's full generative output)
                    out_tokens += (tokens.get("output") or 0) + (tokens.get("thoughts") or 0)

        if msg_count == 0:
            return None

        display_project = summary[:40] if summary else project
        identity = _gemini_identity(_read_auth_mode(_LOCATION.root_dir / "settings.json"))

        return SessionRecord(
            agent      = self.name,
            file_path  = str(path),
            session_id = session_id,
            project    = display_project,
            msg_count  = msg_count,
            first_ts   = first_ts,
            last_ts    = last_ts,
            in_tokens  = in_tokens,
            out_tokens = out_tokens,
            identity_value  = identity.value,
            identity_kind   = identity.kind,
            identity_source = identity.source,
            identity_label  = identity.label,
        )

    def iter_messages(self, path: Path) -> Iterator[MessageRecord]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        for msg in data.get("messages", []):
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "user":
                text = _extract_user_text(msg)
                if text:
                    yield MessageRecord(
                        timestamp = msg.get("timestamp", ""),
                        text      = text,
                    )

    def iter_plans(self) -> Iterator[PlanRecord]:
        # Gemini CLI has no dedicated plan storage
        return iter([])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_user_text(msg: dict) -> str:
    content = msg.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()
    return ""


def _read_auth_mode(settings_path: Path) -> str:
    if not settings_path.exists():
        return ""
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    if not isinstance(data, dict):
        return ""

    security = data.get("security")
    if not isinstance(security, dict):
        return ""

    auth = security.get("auth")
    if not isinstance(auth, dict):
        return ""

    selected = auth.get("selectedType")
    return selected.strip() if isinstance(selected, str) else ""


def _gemini_identity(auth_mode: str):
    if auth_mode:
        return auth_mode_identity(auth_mode, "gemini-settings")
    return unknown_identity("gemini-none")
