"""Command modules and top-level groups."""

from .cache import cache_group
from .doctor import command as doctor_cmd
from .history import command as history_cmd
from .identity import identity_group
from .messages import command as messages_cmd
from .plans import command as plans_cmd
from .sessions import sessions_group
from .setup import setup_group
from .stats import command as stats_cmd

__all__ = [
    "cache_group",
    "doctor_cmd",
    "history_cmd",
    "identity_group",
    "stats_cmd",
    "messages_cmd",
    "plans_cmd",
    "sessions_group",
    "setup_group",
]
