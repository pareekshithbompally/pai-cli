"""Shared data classes used across agents and commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SessionRecord:
    agent: str
    file_path: str
    session_id: str
    account: str
    project: str
    msg_count: int
    first_ts: Optional[str]
    last_ts: Optional[str]
    in_tokens: int
    out_tokens: int


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
