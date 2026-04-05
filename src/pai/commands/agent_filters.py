"""Shared agent-filter helpers for session commands."""

from __future__ import annotations

import click

from ..agents import ALL_AGENTS

_AGENT_CHOICES = ["all", *ALL_AGENTS]


def agent_filter_option(help_text: str = "Filter by one or more agents.") -> callable:
    return click.option(
        "--agent",
        "agent_names",
        multiple=True,
        type=click.Choice(_AGENT_CHOICES, case_sensitive=False),
        help=help_text,
    )


def resolve_agents(agent_names: tuple[str, ...] | list[str] | None) -> list[str]:
    if not agent_names:
        return list(ALL_AGENTS)

    resolved: list[str] = []
    for name in agent_names:
        normalized = name.lower()
        if normalized == "all":
            return list(ALL_AGENTS)
        if normalized not in resolved:
            resolved.append(normalized)
    return resolved or list(ALL_AGENTS)
