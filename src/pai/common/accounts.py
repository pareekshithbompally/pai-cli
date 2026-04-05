"""Identity resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

_UNKNOWN = "—"


@dataclass(frozen=True)
class IdentityInfo:
    value: str = _UNKNOWN
    kind: str = "none"
    source: str = "none"
    label: str | None = None

    @property
    def display(self) -> str:
        return self.label or self.value or _UNKNOWN


def unknown_identity(source: str = "none") -> IdentityInfo:
    return IdentityInfo(source=source)


def session_account_identity(value: str, source: str, *, label: str | None = None) -> IdentityInfo:
    return _identity(value, "session_account", source, label=label)


def global_account_identity(value: str, source: str, *, label: str | None = None) -> IdentityInfo:
    return _identity(value, "global_account", source, label=label)


def auth_state_identity(value: str, source: str, *, label: str | None = None) -> IdentityInfo:
    return _identity(value, "auth_state", source, label=label)


def auth_mode_identity(value: str, source: str, *, label: str | None = None) -> IdentityInfo:
    return _identity(value, "auth_mode", source, label=label)


def provider_identity(value: str, source: str, *, label: str | None = None) -> IdentityInfo:
    return _identity(value, "provider", source, label=label)


def load_claude_accounts(accounts_file: Path) -> dict[str, str]:
    """Return {session_id: raw_email} from an optional session map file."""
    result: dict[str, str] = {}
    if not accounts_file.exists():
        return result

    with accounts_file.open(encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(entry, dict):
                continue

            session_id = str(entry.get("session_id") or "").strip()
            email = str(entry.get("email") or "").strip()
            if session_id and email:
                result[session_id] = email
    return result


def resolve_claude_identity(session_id: str, accounts: dict[str, str]) -> IdentityInfo:
    email = accounts.get(session_id, "").strip()
    if email:
        return session_account_identity(email, "claude-session-map")
    return unknown_identity("claude-none")


def _identity(value: str, kind: str, source: str, *, label: str | None = None) -> IdentityInfo:
    clean = value.strip()
    if not clean:
        return unknown_identity(source)
    return IdentityInfo(value=clean, kind=kind, source=source, label=label)
