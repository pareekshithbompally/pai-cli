"""Abstract base class for all agent adapters.

Each adapter must implement:
  - name          : str identifier ("claude", "codex", etc.)
  - discover_files() -> list[Path]   — fast glob, no file reads
  - parse_session(path) -> SessionRecord | None  — full parse
  - iter_messages(path) -> Iterator[MessageRecord]  — lazy stream

Optional:
  - iter_plans() -> Iterator[PlanRecord]
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator, Optional

from ..common.types import MessageRecord, PlanRecord, SessionRecord


class AgentAdapter(ABC):
    name: str  # Set as class attribute on each subclass

    @abstractmethod
    def discover_files(self) -> list[Path]:
        """Return all session file paths. Fast — no file reads, just globs."""

    @abstractmethod
    def parse_session(self, path: Path) -> Optional[SessionRecord]:
        """Parse a single session file into a SessionRecord.
        Return None if the session has no meaningful content.
        """

    @abstractmethod
    def iter_messages(self, path: Path) -> Iterator[MessageRecord]:
        """Stream user messages from a session file."""

    def iter_plans(self) -> Iterator[PlanRecord]:
        """Yield plan records. Default: nothing."""
        return iter([])
