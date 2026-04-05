"""doctor command — inspect runtime, storage, adapters, cache, and providers."""

from __future__ import annotations

import os
import sqlite3
import sys

import click
from rich.text import Text

from ..agents import ALL_AGENTS, get_adapters
from ..agents.catalog import get_agent_location
from ..billing.pricing import pricing_cache_path
from ..billing.providers import ALL_PROVIDERS, get_providers
from ..common.cache import CACHE_PATH
from ..common.formatting import abbreviate_path, agent_style, fmt_ts, make_table, print_table, provider_style, strip_home
from ..common.identity_config import load_identity_agent_config
from ..common.identity_store import DB_PATH as IDENTITY_DB_PATH, IdentityStore
from ..common.paths import app_cache_dir, app_config_dir, app_data_dir


@click.command("doctor")
def command() -> None:
    """Show environment and storage diagnostics."""
    table = make_table("Section", "Item", "Status", "Detail")

    _add_runtime_section(table)
    table.add_section()
    _add_storage_section(table)
    table.add_section()
    _add_agents_section(table)
    table.add_section()
    _add_identity_section(table)
    table.add_section()
    _add_billing_section(table)

    print_table(table)


def _add_runtime_section(table) -> None:
    table.add_row(
        "Runtime",
        "Python",
        _status_text(True, ok_label="active"),
        Text(abbreviate_path(strip_home(sys.executable), max_len=48), style="dim"),
    )


def _add_storage_section(table) -> None:
    rows = [
        ("Config dir", app_config_dir()),
        ("Data dir", app_data_dir()),
        ("Cache dir", app_cache_dir()),
        ("Sessions DB", CACHE_PATH),
        ("Identity DB", IDENTITY_DB_PATH),
        ("Pricing cache", pricing_cache_path()),
    ]
    for index, (label, path) in enumerate(rows):
        table.add_row(
            "Storage" if index == 0 else "",
            label,
            _status_text(path.exists()),
            Text(abbreviate_path(strip_home(str(path)), max_len=48), style="dim"),
        )


def _add_agents_section(table) -> None:
    cached_counts = _cache_counts()

    for index, adapter in enumerate(get_adapters(ALL_AGENTS)):
        location = get_agent_location(adapter.name)
        style = agent_style(adapter.name)
        root_exists = location.root_dir.exists()
        session_count = len(adapter.discover_files())
        plan_count = len(location.plan_files())
        cached_count = cached_counts.get(adapter.name, 0)

        detail = (
            f"root={abbreviate_path(strip_home(str(location.root_dir)), max_len=24)}  "
            f"sessions={session_count}  plans={plan_count}  cached={cached_count}"
        )

        table.add_row(
            "Agents" if index == 0 else "",
            Text(adapter.name, style=f"bold {style}"),
            _status_text(root_exists, ok_label="ready", bad_label="missing"),
            Text(detail, style="dim"),
        )


def _add_identity_section(table) -> None:
    setup_state = _identity_setup_state()
    for index, agent_name in enumerate(("claude", "gemini")):
        config = load_identity_agent_config(agent_name)
        configured = bool(config)
        transport = config.get("transport", "—")
        runtime = config.get("runtime_mode", "—")
        raw_path = abbreviate_path(strip_home(config.get("raw_path", "—")))
        last_ingest = fmt_ts(setup_state.get(f"identity.{agent_name}.last_ingest_at"))
        detail = (
            f"transport={transport}  runtime={runtime}  "
            f"last_ingest={last_ingest}  raw={raw_path}"
        )
        table.add_row(
            "Identity" if index == 0 else "",
            Text(agent_name, style=f"bold {agent_style(agent_name)}"),
            _status_text(configured, ok_label="configured", bad_label="not set"),
            Text(detail, style="dim"),
        )


def _add_billing_section(table) -> None:
    env_rows = [
        ("openai", "OPENAI_ADMIN_API_KEY"),
        ("anthropic", "ANTHROPIC_ADMIN_API_KEY"),
        ("google", "GOOGLE_BILLING_PROJECT_ID"),
        ("google", "GOOGLE_BILLING_DATASET_ID"),
    ]
    for index, (provider_name, env_name) in enumerate(env_rows):
        value = os.environ.get(env_name)
        table.add_row(
            "Billing env" if index == 0 else "",
            Text(provider_name, style=f"bold {provider_style(provider_name)}"),
            _status_text(bool(value), ok_label="set", bad_label="missing"),
            Text(f"{env_name}={_mask_env_value(value)}", style="dim"),
        )

    table.add_section()
    for index, provider in enumerate(get_providers(ALL_PROVIDERS)):
        ok, reason = provider.is_available()
        detail = "ready" if ok else reason
        table.add_row(
            "Billing" if index == 0 else "",
            Text(provider.name, style=f"bold {provider_style(provider.name)}"),
            _status_text(ok, ok_label="ready", bad_label="unavailable"),
            Text(detail, style="dim" if ok else "yellow"),
        )


def _cache_counts() -> dict[str, int]:
    if not CACHE_PATH.exists():
        return {}

    conn = sqlite3.connect(str(CACHE_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT agent, COUNT(*) AS cnt FROM sessions GROUP BY agent ORDER BY agent"
        ).fetchall()
        return {row["agent"]: row["cnt"] for row in rows}
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def _identity_setup_state() -> dict[str, str | None]:
    if not IDENTITY_DB_PATH.exists():
        return {}

    store = IdentityStore()
    try:
        return store.get_setup_state()
    except sqlite3.Error:
        return {}
    finally:
        store.close()


def _status_text(ok: bool, *, ok_label: str = "yes", bad_label: str = "no") -> Text:
    return Text(ok_label if ok else bad_label, style="green" if ok else "red")


def _mask_env_value(value: str | None) -> str:
    if not value:
        return "—"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"
