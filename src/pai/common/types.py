"""Shared data classes used across agents and commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_UNKNOWN = "—"
_IDENTITY_QUALIFIERS = {
    "session_account": "session",
    "global_account": "account",
    "auth_state": "auth state",
    "auth_mode": "auth mode",
    "provider": "provider",
}


@dataclass
class SessionRecord:
    agent: str
    file_path: str
    session_id: str
    project: str
    msg_count: int
    first_ts: Optional[str]
    last_ts: Optional[str]
    in_tokens: int
    out_tokens: int
    identity_value: str = "—"
    identity_kind: str = "none"
    identity_source: str = "none"
    identity_label: Optional[str] = None

    @property
    def account(self) -> str:
        return self.identity_label or self.identity_value or _UNKNOWN

    @property
    def identity_display(self) -> str:
        return format_identity_display(
            self.identity_value,
            self.identity_kind,
            label=self.identity_label,
        )


def format_identity_display(identity_value: str, identity_kind: str, *, label: Optional[str] = None) -> str:
    base = (label or identity_value or _UNKNOWN).strip() or _UNKNOWN
    raw_value = (identity_value or "").strip()
    qualifier = _IDENTITY_QUALIFIERS.get(identity_kind, "")

    if base == _UNKNOWN:
        return _UNKNOWN
    if label and raw_value and label != raw_value and raw_value != _UNKNOWN:
        decorated = f"{label} [{raw_value}]"
    else:
        decorated = base
    if qualifier:
        return f"{decorated} ({qualifier})"
    return decorated


@dataclass
class MessageRecord:
    timestamp: str
    text: str


@dataclass
class PlanRecord:
    path: str
    title: str
    modified: float   # epoch float from stat
    size: int         # bytes
    agent: str
