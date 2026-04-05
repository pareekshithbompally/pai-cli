"""Identity resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass

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


def _identity(value: str, kind: str, source: str, *, label: str | None = None) -> IdentityInfo:
    clean = value.strip()
    if not clean:
        return unknown_identity(source)
    return IdentityInfo(value=clean, kind=kind, source=source, label=label)
