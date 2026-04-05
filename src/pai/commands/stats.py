"""stats command — aggregate session metrics per identity."""

from __future__ import annotations

from collections import defaultdict

import click
from rich.text import Text

from ..common.cache import SessionCache
from ..common.formatting import agent_style, fmt_int, fmt_tokens, make_table, print_table
from .agent_filters import agent_filter_option, resolve_agents
from .sync import ensure_synced


@click.command("stats")
@click.option("--account", default=None, metavar="LABEL",
              help="Filter by identity or account label.")
@click.option("--project", default=None, metavar="KEYWORD",
              help="Filter by project name.")
@click.option("--no-cache", is_flag=True, default=False,
              help="Force re-parse all sessions.")
@agent_filter_option("Filter by one or more agents. Default: all agents.")
def command(account: str, project: str, no_cache: bool, agent_names: tuple[str, ...]) -> None:
    """Aggregate session stats per identity."""
    agents = resolve_agents(agent_names)
    cache = SessionCache()

    ensure_synced(cache, agents, force=no_cache)

    results = cache.query(agents=agents, account_filter=account, project_filter=project)
    if not results:
        click.echo("No sessions found.")
        return

    multi = len(agents) > 1

    # Aggregate: key = (agent, identity) if multi-agent else (identity,)
    buckets: dict[tuple, dict] = defaultdict(lambda: {
        "sessions": 0, "msgs": 0, "in_tok": 0, "out_tok": 0
    })
    for r in results:
        key = (r.agent, r.identity_display) if multi else (r.identity_display,)
        b = buckets[key]
        b["sessions"] += 1
        b["msgs"]     += r.msg_count
        b["in_tok"]   += r.in_tokens
        b["out_tok"]  += r.out_tokens

    table = make_table(
        *([("Agent")] if multi else []),
        "Identity", "Sessions", "Messages", "In Tokens", "Out Tokens",
    )

    total_sessions = total_msgs = total_in = total_out = 0

    for key in sorted(buckets):
        b = buckets[key]
        row = []
        if multi:
            agent_name = key[0]
            row.append(Text(agent_name, style=f"bold {agent_style(agent_name)}"))
            row.append(Text(key[1], style="dim"))
        else:
            row.append(Text(key[0], style="dim"))

        row += [
            fmt_int(b["sessions"]),
            fmt_int(b["msgs"]),
            fmt_tokens(b["in_tok"]),
            fmt_tokens(b["out_tok"]),
        ]
        table.add_row(*row)

        total_sessions += b["sessions"]
        total_msgs     += b["msgs"]
        total_in       += b["in_tok"]
        total_out      += b["out_tok"]

    # Totals row
    totals: list = []
    if multi:
        totals.append(Text("TOTAL", style="bold"))
        totals.append("")
    else:
        totals.append(Text("TOTAL", style="bold"))
    totals += [
        Text(fmt_int(total_sessions), style="bold"),
        Text(fmt_int(total_msgs),     style="bold"),
        Text(fmt_tokens(total_in),    style="bold"),
        Text(fmt_tokens(total_out),   style="bold"),
    ]
    table.add_section()
    table.add_row(*totals)

    print_table(table)
