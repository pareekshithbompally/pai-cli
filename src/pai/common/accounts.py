"""Account label resolution.

Claude supports multiple accounts via a custom session-accounts.jsonl mapping.
Other agents are single-account; their labels are hardcoded here.
"""

from __future__ import annotations

from pathlib import Path
import json

# Claude: email → display label
CLAUDE_EMAIL_LABELS: dict[str, str] = {
    "pareekshithbompally@gmail.com": "Personal",
    "tech@tatvacare.in": "TatvaCare",
}

# Other agents are single-account — fixed label per agent
AGENT_FIXED_ACCOUNTS: dict[str, str] = {
    "codex":   "TatvaCare",
    "copilot": "Personal",
    "gemini":  "Personal",
    "vibe":    "Personal",
}

_UNKNOWN = "—"


def load_claude_accounts(accounts_file: Path) -> dict[str, str]:
    """Return {session_id: display_label} from session-accounts.jsonl."""
    result: dict[str, str] = {}
    if not accounts_file.exists():
        return result
    with accounts_file.open() as f:
        for line in f:
            try:
                entry = json.loads(line)
                sid   = entry.get("session_id")
                email = entry.get("email", "")
                if sid:
                    result[sid] = CLAUDE_EMAIL_LABELS.get(email) or email or _UNKNOWN
            except (json.JSONDecodeError, AttributeError):
                continue
    return result


def resolve_claude_account(session_id: str, accounts: dict[str, str]) -> str:
    return accounts.get(session_id, _UNKNOWN)


def fixed_account(agent: str) -> str:
    return AGENT_FIXED_ACCOUNTS.get(agent, _UNKNOWN)
