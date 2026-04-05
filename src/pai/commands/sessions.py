"""sessions group — session inspection commands."""

from __future__ import annotations

import click

from .history import command as history_cmd
from .messages import command as messages_cmd
from .plans import command as plans_cmd
from .stats import command as stats_cmd


@click.group("sessions", help="Inspect session history across one or more agents.")
def sessions_group() -> None:
    pass


sessions_group.add_command(history_cmd)
sessions_group.add_command(stats_cmd)
sessions_group.add_command(messages_cmd)
sessions_group.add_command(plans_cmd)
