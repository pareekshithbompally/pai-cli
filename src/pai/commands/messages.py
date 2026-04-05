"""messages command — display user messages from a specific session file."""

from __future__ import annotations

from pathlib import Path

import click
from rich.text import Text

from ..agents import get_adapters
from ..agents.catalog import get_agent_location
from ..common.cache import SessionCache
from ..common.formatting import agent_style, console, fmt_ts, make_table, print_table, truncate
from ..common.types import format_identity_display
from .agent_filters import agent_filter_option, resolve_agents
from .sync import ensure_synced


@click.command("messages")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@agent_filter_option("Prefer one or more agents when resolving the session file.")
def command(file: str, agent_names: tuple[str, ...]) -> None:
    """Show user messages from a session FILE."""
    agents = resolve_agents(agent_names)

    # Identify which adapter owns this file
    adapter = None
    for a in get_adapters(agents):
        if a.name in file or _agent_owns_file(a.name, file):
            adapter = a
            break

    if adapter is None:
        # Fallback: try first agent
        adapter = get_adapters(agents)[0]

    # Look up cached metadata for this session
    cache = SessionCache()
    ensure_synced(cache, [adapter.name], force=False)
    rows_meta = cache._conn.execute(
        """
        SELECT session_id, project, agent, identity_value, identity_kind, identity_label
        FROM sessions
        WHERE file_path = ?
        """,
        (file,),
    ).fetchone()

    if rows_meta:
        agent_name = rows_meta["agent"]
        console.print(Text.assemble(("  Agent   : ", "none"), (agent_name, f"bold {agent_style(agent_name)}")))
        click.echo(
            "  Identity: "
            + format_identity_display(
                rows_meta["identity_value"],
                rows_meta["identity_kind"],
                label=rows_meta["identity_label"],
            )
        )
        click.echo(f"  Project : {rows_meta['project']}")
        click.echo(f"  Session : {rows_meta['session_id']}")
    else:
        click.echo(f"  File    : {file}")
    click.echo()

    msgs = list(adapter.iter_messages(Path(file)))

    if not msgs:
        click.echo("No user messages found.")
        return

    table = make_table("Timestamp (IST)", "Message")
    for m in msgs:
        table.add_row(fmt_ts(m.timestamp), truncate(m.text))

    print_table(table)
    click.echo(f"\n  {len(msgs)} messages")


def _agent_owns_file(agent_name: str, file_path: str) -> bool:
    """Heuristic: check if the file path is under the agent's data directory."""
    root_dir = get_agent_location(agent_name).root_dir
    try:
        Path(file_path).resolve().relative_to(root_dir.resolve())
        return True
    except ValueError:
        return False
