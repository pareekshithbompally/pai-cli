"""GitHub Copilot CLI agent adapter.

Sessions (new format): ~/.copilot/session-state/<uuid>/events.jsonl
Sessions (old format): ~/.copilot/session-state/<uuid>.jsonl  (bare files)
Metadata              : ~/.copilot/session-state/<uuid>/workspace.yaml
Plans                 : ~/.copilot/session-state/<uuid>/plan.md
Tokens                : session.shutdown → data.modelMetrics.<model>.usage
                        Available only in sessions that completed cleanly.
Identity              : login from ~/.copilot/config.json when available
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

from ..common.accounts import global_account_identity, unknown_identity
from ..common.types import MessageRecord, PlanRecord, SessionRecord
from .base import AgentAdapter
from .catalog import get_agent_location

_LOCATION = get_agent_location("copilot")
SESSION_STATE_DIR = _LOCATION.root_dir / "session-state"
CONFIG_FILE = _LOCATION.root_dir / "config.json"


class CopilotAdapter(AgentAdapter):
    name = "copilot"

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover_files(self) -> list[Path]:
        return _LOCATION.session_files()

    # ── Parsing ───────────────────────────────────────────────────────────────

    def parse_session(self, path: Path) -> Optional[SessionRecord]:
        session_id = _session_id_from_path(path)
        project    = _read_cwd_from_workspace(path) or _cwd_from_events(path)
        identity   = _read_copilot_identity(CONFIG_FILE)

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

                    event_type = data.get("type", "")

                    # User messages
                    if event_type == "user.message":
                        content = data.get("data", {}).get("content", "").strip()
                        if content and not content.startswith("/"):
                            msg_count += 1

                    # Shutdown event has aggregated token totals per model
                    if event_type == "session.shutdown":
                        shutdown_tokens = _extract_shutdown_tokens(data)
                        if shutdown_tokens:
                            in_tokens, out_tokens = shutdown_tokens

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
                    if data.get("type") == "user.message":
                        content = data.get("data", {}).get("content", "").strip()
                        if content and not content.startswith("/"):
                            yield MessageRecord(
                                timestamp = data.get("timestamp", ""),
                                text      = content,
                            )
        except OSError:
            return

    # ── Plans ─────────────────────────────────────────────────────────────────

    def iter_plans(self) -> Iterator[PlanRecord]:
        plan_files = _LOCATION.plan_files()
        if not plan_files:
            return
        for plan_md in sorted(plan_files, key=lambda p: p.stat().st_mtime, reverse=True):
            st = plan_md.stat()
            # Use workspace cwd as title context
            cwd = _read_cwd_from_workspace(plan_md.parent / "events.jsonl") or plan_md.parent.name
            yield PlanRecord(
                path     = str(plan_md),
                title    = cwd,
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


def _session_id_from_path(path: Path) -> str:
    # new: session-state/<uuid>/events.jsonl → parent is <uuid>
    if path.name == "events.jsonl":
        return path.parent.name
    # old: session-state/<uuid>.jsonl
    return path.stem


def _read_cwd_from_workspace(events_path: Path) -> str:
    """Read cwd from workspace.yaml sibling file (new format sessions)."""
    workspace = events_path.parent / "workspace.yaml"
    if not workspace.exists():
        return ""
    try:
        for line in workspace.read_text().splitlines():
            if line.startswith("cwd:"):
                val = line.split(":", 1)[1].strip()
                return _abbreviate_path(val)
    except OSError:
        pass
    return ""


def _cwd_from_events(path: Path) -> str:
    """Fallback: scan events for first hook or session event with cwd."""
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                data = _parse_line(line)
                if data is None:
                    continue
                # hook.start events carry cwd
                if data.get("type") == "hook.start":
                    cwd = data.get("data", {}).get("input", {}).get("cwd", "")
                    if cwd:
                        return _abbreviate_path(cwd)
    except OSError:
        pass
    return "—"


def _extract_shutdown_tokens(data: dict) -> Optional[tuple[int, int]]:
    """Sum tokens across all models in session.shutdown modelMetrics."""
    metrics = data.get("data", {}).get("modelMetrics")
    if not isinstance(metrics, dict):
        return None
    total_in = total_out = 0
    for model_data in metrics.values():
        usage = model_data.get("usage", {})
        total_in  += (usage.get("inputTokens") or 0) + (usage.get("cacheReadTokens") or 0)
        total_out += (usage.get("outputTokens") or 0)
    return (total_in, total_out) if (total_in or total_out) else None


def _abbreviate_path(path: str) -> str:
    import os
    home = os.path.expanduser("~")
    path = path.replace(home, "~")
    if len(path) > 36:
        path = path[:10] + "…" + path[-24:]
    return path


def _read_copilot_identity(config_path: Path):
    if not config_path.exists():
        return unknown_identity("copilot-none")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return unknown_identity("copilot-none")

    if not isinstance(data, dict):
        return unknown_identity("copilot-none")

    last = data.get("last_logged_in_user")
    if isinstance(last, dict):
        login = last.get("login")
        if isinstance(login, str) and login.strip():
            return global_account_identity(login, "copilot-config")

    users = data.get("logged_in_users")
    if isinstance(users, list):
        for entry in users:
            if not isinstance(entry, dict):
                continue
            login = entry.get("login")
            if isinstance(login, str) and login.strip():
                return global_account_identity(login, "copilot-config")

    return unknown_identity("copilot-none")
