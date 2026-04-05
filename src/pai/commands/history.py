"""history command — list recent sessions across one or more agents."""

from __future__ import annotations

import click
from rich.text import Text

from ..common.cache import SessionCache
from ..common.formatting import (
    TRUNCATE_WIDTHS,
    agent_style,
    fmt_tokens,
    fmt_ts,
    make_table,
    print_table,
    truncate,
)
from ..common.types import SessionRecord
from .agent_filters import agent_filter_option, resolve_agents
from .sync import ensure_synced


@click.command("history")
@click.option("-n", default=10, show_default=True, metavar="N",
              help="Sessions to show (0 = all).")
@click.option("--account", default=None, metavar="LABEL",
              help="Filter by identity or account label.")
@click.option("--project", default=None, metavar="KEYWORD",
              help="Filter by project name.")
@click.option("--no-cache", is_flag=True, default=False,
              help="Force re-parse all sessions.")
@agent_filter_option("Filter by one or more agents. Default: all agents.")
def command(n: int, account: str, project: str, no_cache: bool, agent_names: tuple[str, ...]) -> None:
    """List recent sessions."""
    agents = resolve_agents(agent_names)
    cache = SessionCache()

    ensure_synced(cache, agents, force=no_cache)

    results = cache.query(agents=agents, account_filter=account, project_filter=project)
    if not results:
        click.echo("No sessions found.")
        return

    shown = results if n == 0 else results[:n]
    multi = len(agents) > 1

    table = make_table(
        *([("Agent")] if multi else []),
        "Identity", "Project", "Session", "Msgs",
        "First (IST)", "Last (IST)", "In Tok", "Out Tok",
    )

    for r in shown:
        row = _build_row(r, multi)
        table.add_row(*row)

    print_table(table)

    if n and len(results) > n:
        click.echo(f"\n  Showing {n} of {len(results)} sessions  ·  use -n 0 for all")


def _build_row(r: SessionRecord, include_agent: bool) -> list[str | Text]:
    style = agent_style(r.agent)
    row: list[str | Text] = []
    if include_agent:
        row.append(Text(r.agent, style=f"bold {style}"))
    row += [
        Text(truncate(r.identity_display, TRUNCATE_WIDTHS["account"]), style="dim"),
        Text(truncate(r.project, TRUNCATE_WIDTHS["project"]), style=style),
        Text(r.session_id[:8], style="dim"),
        str(r.msg_count),
        fmt_ts(r.first_ts),
        fmt_ts(r.last_ts),
        fmt_tokens(r.in_tokens),
        fmt_tokens(r.out_tokens),
    ]
    return row
