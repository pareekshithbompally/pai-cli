"""plans command — list and inspect saved plans across agents."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
from rich.syntax import Syntax
from rich.text import Text

from ..agents import get_adapters
from ..common.formatting import agent_style, console, make_table, print_table, strip_home, truncate
from .agent_filters import agent_filter_option, resolve_agents


@click.command("plans")
@click.option("--keyword", default=None, metavar="KW",
              help="Filter by keyword in title or path.")
@click.option("--show", default=None, metavar="PATH",
              help="Print the full content of a plan file.")
@agent_filter_option("Filter by one or more agents. Default: all agents.")
def command(keyword: str, show: str, agent_names: tuple[str, ...]) -> None:
    """List saved plans, or show a plan's content with --show PATH."""
    agents = resolve_agents(agent_names)

    if show:
        _print_plan_content(show)
        return

    multi = len(agents) > 1
    kw = keyword.lower() if keyword else None
    rows_data = []

    for adapter in get_adapters(agents):
        for plan in adapter.iter_plans():
            label = f"{plan.agent}/{plan.title}" if multi else plan.title
            if kw and kw not in label.lower() and kw not in plan.path.lower():
                continue
            rows_data.append((adapter.name, plan))

    if not rows_data:
        msg = f"No plans matching '{keyword}'." if keyword else "No plans found."
        click.echo(msg)
        return

    table = make_table(
        *([("Agent")] if multi else []),
        "#", "Modified", "Size", "Title", "Path",
    )

    for i, (agent_name, plan) in enumerate(rows_data, 1):
        modified = datetime.fromtimestamp(plan.modified).strftime("%Y-%m-%d %H:%M")
        size_str = f"{plan.size / 1024:.1f}kb"
        title    = truncate(plan.title, 48)
        path_str = truncate(strip_home(plan.path), 50)

        row = []
        if multi:
            row.append(Text(agent_name, style=f"bold {agent_style(agent_name)}"))
        row += [
            Text(str(i), style="dim"),
            modified,
            Text(size_str, style="dim"),
            title,
            Text(path_str, style="dim"),
        ]
        table.add_row(*row)

    print_table(table)
    click.echo(f"\n  {len(rows_data)} plan(s)  ·  use --show <path> to read")


def _print_plan_content(path_str: str) -> None:
    path = Path(path_str).expanduser()
    if not path.exists():
        click.echo(f"File not found: {path}", err=True)
        raise SystemExit(1)
    content = path.read_text(errors="replace")
    console.print(Syntax(content, "markdown", theme="monokai", word_wrap=True))
