"""identity group — alias management for normalized identities."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click
from rich.text import Text

from ..agents import ALL_AGENTS
from ..common.cache import SessionCache
from ..common.formatting import agent_style, fmt_ts, make_table, print_table
from ..common.identity_config import (
    identity_agent_config_path,
    identity_collector_config_path,
    identity_raw_path,
    load_identity_agent_config,
)
from ..common.identity_store import IdentityStore

_TELEMETRY_AGENTS = ("claude", "gemini")


@click.group("identity", help="Manage identity aliases and related state.")
def identity_group() -> None:
    pass


@identity_group.group("alias", help="Manage identity aliases.")
def alias_group() -> None:
    pass


@alias_group.command("set")
@click.option(
    "--agent",
    required=True,
    type=click.Choice(ALL_AGENTS, case_sensitive=False),
    help="Agent whose identity value should be aliased.",
)
@click.argument("raw_value")
@click.argument("label")
def alias_set(agent: str, raw_value: str, label: str) -> None:
    """Set or update an alias for a raw identity value."""
    agent = agent.lower()
    store = IdentityStore()
    try:
        store.set_alias(agent, raw_value, label, updated_at=_now_iso())
    finally:
        store.close()

    cache = SessionCache()
    cache.apply_identity_overrides([agent])
    click.echo(f"Saved alias for {agent}: {raw_value} -> {label}")


@alias_group.command("list")
@click.option(
    "--agent",
    default=None,
    type=click.Choice(ALL_AGENTS, case_sensitive=False),
    help="Show aliases for one agent only.",
)
def alias_list(agent: str | None) -> None:
    """List configured identity aliases."""
    store = IdentityStore()
    try:
        rows = store.list_aliases(agent.lower() if agent else None)
    finally:
        store.close()

    if not rows:
        click.echo("No identity aliases configured.")
        return

    table = make_table("Agent", "Raw value", "Label", "Updated")
    for row in rows:
        table.add_row(
            Text(row["agent"], style=f"bold {agent_style(row['agent'])}"),
            row["raw_value"],
            row["label"],
            fmt_ts(row["updated_at"]),
        )
    print_table(table)


@alias_group.command("remove")
@click.option(
    "--agent",
    required=True,
    type=click.Choice(ALL_AGENTS, case_sensitive=False),
    help="Agent whose alias should be removed.",
)
@click.argument("raw_value")
def alias_remove(agent: str, raw_value: str) -> None:
    """Remove an alias for a raw identity value."""
    agent = agent.lower()
    store = IdentityStore()
    try:
        removed = store.remove_alias(agent, raw_value)
    finally:
        store.close()

    cache = SessionCache()
    cache.apply_identity_overrides([agent])
    if removed:
        click.echo(f"Removed alias for {agent}: {raw_value}")
    else:
        click.echo(f"No alias found for {agent}: {raw_value}")


@identity_group.command("clear")
@click.option(
    "--agent",
    default=None,
    type=click.Choice(_TELEMETRY_AGENTS, case_sensitive=False),
    help="Clear one telemetry-backed agent only.",
)
@click.option(
    "--include-aliases",
    is_flag=True,
    default=False,
    help="Also remove aliases for the selected agent(s).",
)
@click.option(
    "--include-setup",
    is_flag=True,
    default=False,
    help="Also remove saved setup state for the selected agent(s).",
)
def identity_clear(agent: str | None, include_aliases: bool, include_setup: bool) -> None:
    """Clear ingested identity telemetry state and raw files."""
    target_agent = agent.lower() if agent else None
    target_agents = [target_agent] if target_agent else list(_TELEMETRY_AGENTS)

    raw_removed = 0
    config_removed = 0
    for current_agent in target_agents:
        raw_path = _configured_raw_path(current_agent)
        if raw_path.exists():
            raw_path.unlink()
            raw_removed += 1
        if include_setup:
            config_path = identity_agent_config_path(current_agent)
            if config_path.exists():
                config_path.unlink()
                config_removed += 1
            collector_config_path = identity_collector_config_path(current_agent)
            if collector_config_path.exists():
                collector_config_path.unlink()
                config_removed += 1

    store = IdentityStore()
    try:
        counts = store.clear_identity_data(
            target_agent,
            include_aliases=include_aliases,
            include_setup=include_setup,
        )
    finally:
        store.close()

    cache = SessionCache()
    if target_agent:
        cleared_sessions = cache.clear(agent=target_agent)
    else:
        cleared_sessions = sum(cache.clear(agent=current_agent) for current_agent in target_agents)

    scope = target_agent or "claude + gemini"
    click.echo(f"Cleared identity telemetry state for {scope}.")
    click.echo(
        "  "
        + "  ".join(
            [
                f"events={counts['events']}",
                f"offsets={counts['offsets']}",
                f"raw_files={raw_removed}",
                f"session_cache={cleared_sessions}",
                f"aliases={counts['aliases']}",
                f"setup={counts['setup'] + config_removed}",
            ]
        )
    )


def _configured_raw_path(agent: str) -> Path:
    config = load_identity_agent_config(agent)
    raw_path = config.get("raw_path")
    return Path(raw_path) if raw_path else identity_raw_path(agent)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
