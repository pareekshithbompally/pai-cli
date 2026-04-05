"""Codex (OpenAI) agent adapter.

Sessions  : ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
Index     : ~/.codex/session_index.jsonl  (thread_name per session id)
Plans     : ~/.codex/plans/*/  (feature directories with markdown)

Event model (per session JSONL):
  - turn_context      : one per user turn; carries cwd. Count = msg_count.
  - response_item     : role=user, first after turn_context = real user message
  - event_msg         : type=token_count carries cumulative token totals (take last)
  - session_meta      : first event; carries cwd as fallback project name

Tokens    : event_msg type=token_count → payload.info.total_token_usage (last seen)
Account   : always "TatvaCare" (single account)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

from ..common.accounts import fixed_account
from ..common.types import MessageRecord, PlanRecord, SessionRecord
from .base import AgentAdapter
from .catalog import get_agent_location

_LOCATION = get_agent_location("codex")
SESSION_INDEX = _LOCATION.files["session_index"]


class CodexAdapter(AgentAdapter):
    name = "codex"

    def __init__(self) -> None:
        self._index: Optional[dict[str, str]] = None  # session_id → thread_name

    @property
    def index(self) -> dict[str, str]:
        if self._index is None:
            self._index = _load_session_index(SESSION_INDEX)
        return self._index

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover_files(self) -> list[Path]:
        return _LOCATION.session_files()

    # ── Parsing ───────────────────────────────────────────────────────────────

    def parse_session(self, path: Path) -> Optional[SessionRecord]:
        session_id = _session_id_from_path(path)
        thread     = self.index.get(session_id, "")

        msg_count = 0
        first_ts = last_ts = None
        in_tokens = out_tokens = 0
        cwd = ""
        last_usage: Optional[dict] = None

        try:
            with path.open(encoding="utf-8") as f:
                for line in f:
                    data = _parse_line(line)
                    if data is None:
                        continue

                    ts = data.get("timestamp")
                    if ts:
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts

                    event_type = data.get("type", "")
                    payload    = data.get("payload") or {}

                    # session_meta carries cwd as fallback project
                    if event_type == "session_meta" and not cwd:
                        cwd = payload.get("cwd", "")

                    # Each turn_context = one real user interaction
                    elif event_type == "turn_context":
                        msg_count += 1
                        if not cwd:
                            cwd = payload.get("cwd", "")

                    # Token counts: cumulative totals, keep last seen
                    elif event_type == "event_msg" and payload.get("type") == "token_count":
                        usage = (payload.get("info") or {}).get("total_token_usage")
                        if isinstance(usage, dict):
                            last_usage = usage

        except OSError:
            return None

        if msg_count == 0:
            return None

        if last_usage:
            in_tokens  = (last_usage.get("input_tokens") or 0) + (last_usage.get("cached_input_tokens") or 0)
            out_tokens = (last_usage.get("output_tokens") or 0) + (last_usage.get("reasoning_output_tokens") or 0)

        display_project = thread or _abbreviate_path(cwd) or _project_from_path(path)

        return SessionRecord(
            agent      = self.name,
            file_path  = str(path),
            session_id = session_id,
            account    = fixed_account(self.name),
            project    = display_project,
            msg_count  = msg_count,
            first_ts   = first_ts,
            last_ts    = last_ts,
            in_tokens  = in_tokens,
            out_tokens = out_tokens,
        )

    def iter_messages(self, path: Path) -> Iterator[MessageRecord]:
        """Yield the first real user response_item after each turn_context."""
        try:
            in_turn = False
            with path.open(encoding="utf-8") as f:
                for line in f:
                    data = _parse_line(line)
                    if data is None:
                        continue

                    event_type = data.get("type", "")
                    payload    = data.get("payload") or {}

                    if event_type == "turn_context":
                        in_turn = True
                        continue

                    if in_turn and event_type == "response_item" and payload.get("role") == "user":
                        text = _extract_user_text(payload)
                        if text:
                            yield MessageRecord(
                                timestamp = data.get("timestamp", ""),
                                text      = text,
                            )
                            in_turn = False  # consumed the turn's real message

        except OSError:
            return

    # ── Plans ─────────────────────────────────────────────────────────────────

    def iter_plans(self) -> Iterator[PlanRecord]:
        plan_files = _LOCATION.plan_files()
        if not plan_files:
            return
        for md_file in sorted(plan_files, key=lambda p: p.stat().st_mtime, reverse=True):
            st = md_file.stat()
            yield PlanRecord(
                path     = str(md_file),
                title    = f"{md_file.parent.name} / {md_file.stem}",
                modified = st.st_mtime,
                size     = st.st_size,
                agent    = self.name,
            )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_line(line: str) -> Optional[dict]:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _load_session_index(path: Path) -> dict[str, str]:
    index: dict[str, str] = {}
    if not path.exists():
        return index
    with path.open() as f:
        for line in f:
            try:
                entry = json.loads(line)
                sid = entry.get("id", "")
                if sid:
                    index[sid] = entry.get("thread_name", "")
            except json.JSONDecodeError:
                continue
    return index


def _session_id_from_path(path: Path) -> str:
    """Extract UUID from rollout-YYYY-MM-DDTHH-MM-SS-<uuid>.jsonl.

    Filename structure: rollout-{date}-{uuid} where uuid is 5 hex groups.
    Split on '-' and take last 5 segments.
    """
    parts = path.stem.split("-")
    # UUID portion: last 5 dash-separated groups (8-4-4-4-12 hex chars)
    if len(parts) >= 5:
        return "-".join(parts[-5:])
    return path.stem


def _project_from_path(path: Path) -> str:
    """Date fallback: YYYY/MM/DD from path."""
    parts = path.parts
    try:
        idx = parts.index("sessions")
        return "/".join(parts[idx + 1: idx + 4])
    except ValueError:
        return path.parent.name


def _abbreviate_path(path: str) -> str:
    if not path:
        return ""
    import os
    path = path.replace(os.path.expanduser("~"), "~")
    if len(path) > 36:
        path = path[:10] + "…" + path[-24:]
    return path


def _extract_user_text(payload: dict) -> str:
    """Extract real user text from a response_item payload, skip injected blocks."""
    for item in payload.get("content") or []:
        if not isinstance(item, dict) or item.get("type") != "input_text":
            continue
        text = item.get("text", "").strip()
        # Skip system-injected context: XML blocks, AGENTS.md dumps, env context
        if not text or text.startswith("<") or text.startswith("# AGENTS.md"):
            continue
        return text
    return ""
