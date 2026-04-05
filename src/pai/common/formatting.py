"""Rich-based output formatting utilities."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table, box
IST = timezone(timedelta(hours=5, minutes=30))
MSG_TRUNCATE = 100
PATH_HEAD = 10
PATH_TAIL = 22

console = Console()


# ── Timestamp helpers ─────────────────────────────────────────────────────────

def to_ist(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(IST)
    except ValueError:
        return None


def fmt_dt(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"


def fmt_ts(ts: Optional[str]) -> str:
    return fmt_dt(to_ist(ts))


# ── Path helpers ──────────────────────────────────────────────────────────────

def abbreviate_path(path: str, max_len: int = 36) -> str:
    """Shorten a long path: keep head + tail, replace middle with '…'."""
    if len(path) <= max_len:
        return path
    return path[:PATH_HEAD] + "…" + path[-(PATH_TAIL):]


def strip_home(path: str) -> str:
    import os
    home = os.path.expanduser("~")
    return path.replace(home, "~")


# ── Number helpers ────────────────────────────────────────────────────────────

def fmt_tokens(n: int) -> str:
    if n == 0:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def fmt_int(n: int) -> str:
    return f"{n:,}"


# ── Text helpers ──────────────────────────────────────────────────────────────

def truncate(text: str, width: int = MSG_TRUNCATE) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


# ── Table builders ────────────────────────────────────────────────────────────

BRAND_COLORS = {
    "claude": "rgb(205,124,94)",
    "gemini": "rgb(81,139,244)",
    "codex": "rgb(255,255,255)",
    "vibe": "rgb(243,180,68)",
    "copilot": "rgb(236,85,247)",
}

PROVIDER_BRAND_ALIASES = {
    "anthropic": "claude",
    "google": "gemini",
    "openai": "codex",
}


def brand_style(name: str) -> str:
    normalized = name.lower()
    brand_key = PROVIDER_BRAND_ALIASES.get(normalized, normalized)
    return BRAND_COLORS.get(brand_key, "white")


def agent_style(agent: str) -> str:
    return brand_style(agent)


def provider_style(provider: str) -> str:
    return brand_style(provider)


# Pre-truncation widths applied by row builders (not by Rich).
# All columns are no_wrap=True — Rich must never fold or collapse any column.
# Callers are responsible for truncating before passing to table.add_row().
TRUNCATE_WIDTHS: dict[str, int] = {
    "project":  26,
    "title":    44,
    "path":     48,
    "message":  80,
    "account":  48,
}


def make_table(*columns: str, title: str = "", show_edge: bool = True) -> Table:
    """Create a styled Rich table. All columns are no_wrap; callers pre-truncate."""
    t = Table(
        box=box.SIMPLE_HEAD,
        show_edge=show_edge,
        header_style="bold white",
        title=title or None,
        title_style="bold",
        expand=False,
        min_width=40,
    )
    for col in columns:
        t.add_column(col, no_wrap=True)
    return t


def print_table(table: Table) -> None:
    console.print(table)


@contextmanager
def spinner_status(message: str) -> Iterator[None]:
    """Render a transient spinner line for short-lived fetch/load phases."""
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[dim]{task.description}[/dim]"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Fetching {message}…", total=None)
        yield
