"""cache group — cache inspection and maintenance."""

from __future__ import annotations

import click
from rich.text import Text

from ..agents import ALL_AGENTS
from ..common.cache import CACHE_PATH, SessionCache
from ..common.formatting import agent_style, make_table, print_table


@click.group("cache", help="Manage the session cache.")
def cache_group() -> None:
    pass


@cache_group.command("clear")
@click.option(
    "--agent",
    default=None,
    type=click.Choice(ALL_AGENTS, case_sensitive=False),
    help="Clear only a specific agent's cache.",
)
def cache_clear(agent: str) -> None:
    """Delete cached session data (will be rebuilt on next run)."""
    cache = SessionCache()
    count = cache.clear(agent=agent)
    scope = agent or "all agents"
    click.echo(f"Cleared {count} cached session(s) for {scope}.")


@cache_group.command("info")
def cache_info() -> None:
    """Show cache location and per-agent row counts."""
    click.echo(f"  Cache : {CACHE_PATH}")
    click.echo()

    cache = SessionCache()
    summary = cache.stats_summary()

    if not summary:
        click.echo("  Cache is empty.")
        return

    table = make_table("Agent", "Cached Sessions")
    total = 0
    for row in summary:
        name = row["agent"]
        cnt = row["cnt"]
        total += cnt
        table.add_row(
            Text(name, style=f"bold {agent_style(name)}"),
            str(cnt),
        )
    table.add_section()
    table.add_row(Text("TOTAL", style="bold"), Text(str(total), style="bold"))
    print_table(table)
