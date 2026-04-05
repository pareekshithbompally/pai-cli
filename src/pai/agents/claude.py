"""Claude Code agent adapter.

Sessions  : ~/.claude/projects/**/*.jsonl
Accounts  : optional session->email map file
Plans     : ~/.claude/plans/*.md
Tokens    : per-response usage.{input,cache_creation_input,cache_read_input,output}_tokens
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

from ..common.accounts import load_claude_accounts, resolve_claude_identity
from ..common.types import MessageRecord, PlanRecord, SessionRecord
from .base import AgentAdapter
from .catalog import get_agent_location

_LOCATION = get_agent_location("claude")
PROJECTS_DIR = _LOCATION.root_dir / "projects"
ACCOUNTS_FILE = _LOCATION.files["accounts"]


class ClaudeAdapter(AgentAdapter):
    name = "claude"

    def __init__(self) -> None:
        self._accounts: Optional[dict[str, str]] = None

    @property
    def accounts(self) -> dict[str, str]:
        if self._accounts is None:
            self._accounts = load_claude_accounts(ACCOUNTS_FILE)
        return self._accounts or {}

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover_files(self) -> list[Path]:
        return _LOCATION.session_files()

    # ── Parsing ───────────────────────────────────────────────────────────────

    def parse_session(self, path: Path) -> Optional[SessionRecord]:
        session_id = path.stem
        identity   = resolve_claude_identity(session_id, self.accounts)
        project    = _abbreviate_project(path.parent.name)

        msg_count = 0
        first_ts = last_ts = None
        in_tokens = out_tokens = 0

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

                    if _is_user_message(data):
                        msg_count += 1

                    usage = _extract_usage(data)
                    if usage:
                        in_tokens  += _sum_input_tokens(usage)
                        out_tokens += usage.get("output_tokens") or 0
        except OSError:
            return None

        if msg_count == 0:
            return None

        return SessionRecord(
            agent      = self.name,
            file_path  = str(path),
            session_id = session_id,
            project    = project,
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
            with path.open(encoding="utf-8") as f:
                for line in f:
                    data = _parse_line(line)
                    if data is None:
                        continue
                    ok, text = _user_message_text(data)
                    if ok:
                        yield MessageRecord(
                            timestamp = data.get("timestamp", ""),
                            text      = text,
                        )
        except OSError:
            return

    # ── Plans ─────────────────────────────────────────────────────────────────

    def iter_plans(self) -> Iterator[PlanRecord]:
        plan_files = _LOCATION.plan_files()
        if not plan_files:
            return
        for p in sorted(plan_files, key=lambda x: x.stat().st_mtime, reverse=True):
            st = p.stat()
            yield PlanRecord(
                path     = str(p),
                title    = _extract_md_title(p),
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


def _is_user_message(data: dict) -> bool:
    _, text = _user_message_text(data)
    return bool(text)


def _user_message_text(data: dict) -> tuple[bool, str]:
    """Return (is_real, text). Filters tool results and empty messages."""
    if data.get("type") != "user":
        return False, ""
    msg = data.get("message")
    if not isinstance(msg, dict) or msg.get("role") != "user":
        return False, ""
    content = msg.get("content", "")

    if isinstance(content, str):
        text = content.strip()
        if "<local-command-" in text or not text:
            return False, ""
        return True, text

    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_result":
                return False, ""
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
        text = "".join(parts).strip()
        return bool(text), text

    return False, ""


def _extract_usage(data: dict) -> Optional[dict]:
    msg = data.get("message")
    if isinstance(msg, dict):
        u = msg.get("usage")
        if isinstance(u, dict):
            return u
    u = data.get("usage")
    if isinstance(u, dict):
        return u
    return None


def _sum_input_tokens(usage: dict) -> int:
    return (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
    )


def _abbreviate_project(dir_name: str) -> str:
    """~/.claude/projects stores dirs with '-' replacing '/'."""
    name = dir_name.replace("-Users-dhspl-", "…/")
    if len(name) > 36:
        name = name[:10] + "…" + name[-24:]
    return name


def _extract_md_title(path: Path) -> str:
    try:
        for line in path.read_text(errors="replace").splitlines():
            s = line.strip()
            if s.startswith("# "):
                return s[2:].strip()
    except OSError:
        pass
    return path.stem
