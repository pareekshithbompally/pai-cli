"""setup group — guided setup flows."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import shutil
from pathlib import Path

import click
from rich.text import Text

from ..common.formatting import abbreviate_path, make_table, print_table, strip_home
from ..common.identity_config import (
    identity_agent_config_path,
    identity_collector_config_path,
    identity_config_dir,
    identity_data_dir,
    identity_raw_path,
    load_identity_agent_config,
)
from ..common.identity_store import IdentityStore
from ..common.paths import app_cache_path

CLAUDE_AGENT = "claude"
GEMINI_AGENT = "gemini"


@click.group("setup", help="Guided setup flows.")
def setup_group() -> None:
    pass


@setup_group.command("identity")
def setup_identity() -> None:
    """Configure telemetry-backed identity capture for Claude and Gemini."""
    click.echo()
    click.echo("Identity setup")
    click.echo(f"  Config : {strip_home(str(identity_config_dir()))}")
    click.echo(f"  Data   : {strip_home(str(identity_data_dir()))}")
    click.echo()

    while True:
        _print_identity_status()
        click.echo()
        click.echo("Configure")
        click.echo("  1  Claude")
        click.echo("  2  Gemini")
        click.echo("  3  Claude + Gemini")
        click.echo("  q  Done")
        click.echo()

        choice = click.prompt("  Select option", prompt_suffix=": ", default="q", show_default=False).strip().lower()
        if choice in {"q", ""}:
            break
        if choice == "1":
            _configure_claude()
            continue
        if choice == "2":
            _configure_gemini()
            continue
        if choice == "3":
            _configure_claude()
            click.echo()
            _configure_gemini()
            continue
        click.echo("  Invalid choice.")


def _configure_claude() -> None:
    click.echo()
    click.echo("Claude identity setup")

    binary = shutil.which("otelcol-contrib") or shutil.which("otelcol")
    docker = shutil.which("docker")
    options: list[tuple[str, str, str | None]] = []
    if binary:
        options.append(("Local collector (Recommended)", "collector-binary", binary))
    if docker:
        options.append(("Docker collector", "collector-docker", docker))
    options.append(("Manual collector config", "collector-manual", None))

    for idx, (label, _, _) in enumerate(options, start=1):
        click.echo(f"  {idx}  {label}")
    click.echo()

    selected = _prompt_index("  Select transport", len(options))
    transport, runner = options[selected - 1][1], options[selected - 1][2]

    runtime_mode = "config-only"
    if transport != "collector-manual":
        click.echo()
        click.echo("Collector runtime")
        click.echo("  1  Background service")
        click.echo("  2  Manual start/stop")
        click.echo("  3  Config only")
        click.echo()
        runtime_mode = {
            1: "background",
            2: "manual",
            3: "config-only",
        }[_prompt_index("  Select runtime", 3)]

    raw_path = identity_raw_path(CLAUDE_AGENT)
    config_path = identity_collector_config_path(CLAUDE_AGENT)
    cache_log_path = app_cache_path("identity", "claude-collector.log")
    _ensure_parent_dirs(raw_path, config_path, cache_log_path, identity_agent_config_path(CLAUDE_AGENT))

    collector_yaml = _claude_collector_yaml(raw_path, transport)
    config_payload = {
        "agent": CLAUDE_AGENT,
        "transport": transport,
        "runtime_mode": runtime_mode,
        "endpoint": "http://localhost:4317",
        "raw_path": str(raw_path),
        "collector_config": str(config_path),
        "runner": runner,
        "configured_at": _now_iso(),
    }

    _write_text(config_path, collector_yaml)
    _write_json(identity_agent_config_path(CLAUDE_AGENT), config_payload)
    _save_setup_state(CLAUDE_AGENT, config_payload)

    click.echo()
    click.echo(f"  Saved collector config : {strip_home(str(config_path))}")
    click.echo(f"  Raw telemetry file     : {strip_home(str(raw_path))}")
    click.echo()
    click.echo("Claude telemetry env")
    _print_snippet(
        [
            "export CLAUDE_CODE_ENABLE_TELEMETRY=1",
            "export OTEL_LOGS_EXPORTER=otlp",
            "export OTEL_EXPORTER_OTLP_PROTOCOL=grpc",
            "export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317",
        ]
    )

    click.echo()
    click.echo("Collector command")
    if transport == "collector-binary" and runner:
        _print_snippet([f"{runner} --config {config_path}"])
        if runtime_mode == "background":
            click.echo(f"  Background hint: nohup {runner} --config {config_path} > {cache_log_path} 2>&1 &")
    elif transport == "collector-docker":
        docker_cmd = _claude_docker_command(config_path, raw_path)
        _print_snippet([docker_cmd])
    else:
        click.echo("  Use the saved collector config with any OTLP-compatible collector.")

    click.echo()
    click.echo("  Claude identity setup saved.")


def _configure_gemini() -> None:
    click.echo()
    click.echo("Gemini identity setup")

    raw_path = identity_raw_path(GEMINI_AGENT)
    config_payload = {
        "agent": GEMINI_AGENT,
        "transport": "direct-file",
        "runtime_mode": "n/a",
        "raw_path": str(raw_path),
        "configured_at": _now_iso(),
    }

    _ensure_parent_dirs(raw_path, identity_agent_config_path(GEMINI_AGENT))
    _write_json(identity_agent_config_path(GEMINI_AGENT), config_payload)
    _save_setup_state(GEMINI_AGENT, config_payload)

    click.echo()
    click.echo(f"  Raw telemetry file : {strip_home(str(raw_path))}")
    click.echo()
    click.echo("Gemini telemetry env")
    _print_snippet(
        [
            "export GEMINI_TELEMETRY_ENABLED=true",
            "export GEMINI_TELEMETRY_TARGET=local",
            f"export GEMINI_TELEMETRY_OUTFILE={raw_path}",
        ]
    )
    click.echo()
    click.echo("Gemini settings.json alternative")
    _print_snippet(
        [
            "{",
            '  "telemetry": {',
            '    "enabled": true,',
            '    "target": "local",',
            f'    "outfile": "{raw_path}"',
            "  }",
            "}",
        ]
    )
    click.echo()
    click.echo("  Gemini identity setup saved.")


def _print_identity_status() -> None:
    table = make_table("Agent", "Configured", "Transport", "Runtime", "Raw output")
    for agent in (CLAUDE_AGENT, GEMINI_AGENT):
        config = load_identity_agent_config(agent)
        configured = bool(config)
        table.add_row(
            agent,
            Text("● configured" if configured else "○ not set", style="green" if configured else "dim"),
            config.get("transport", "—"),
            config.get("runtime_mode", "—"),
            abbreviate_path(strip_home(config.get("raw_path", "—"))),
        )
    print_table(table)

def _save_setup_state(agent: str, payload: dict[str, str | None]) -> None:
    store = IdentityStore()
    try:
        for key, value in payload.items():
            store.set_setup_value(f"identity.{agent}.{key}", None if value is None else str(value), updated_at=_now_iso())
    finally:
        store.close()

def _claude_collector_yaml(raw_path: Path, transport: str) -> str:
    output_path = "/pai-data/claude-otel.jsonl" if transport == "collector-docker" else str(raw_path)
    return "\n".join(
        [
            "receivers:",
            "  otlp:",
            "    protocols:",
            "      grpc:",
            "        endpoint: 0.0.0.0:4317",
            "",
            "exporters:",
            "  file/logs:",
            f"    path: {json.dumps(output_path)}",
            "",
            "service:",
            "  pipelines:",
            "    logs:",
            "      receivers: [otlp]",
            "      exporters: [file/logs]",
            "",
        ]
    )


def _claude_docker_command(config_path: Path, raw_path: Path) -> str:
    host_raw_dir = raw_path.parent
    return (
        "docker run -d --name pai-claude-otel "
        "-p 4317:4317 "
        f"-v {config_path}:/etc/otelcol-contrib/config.yaml:ro "
        f"-v {host_raw_dir}:/pai-data "
        "otel/opentelemetry-collector-contrib:latest "
        "--config /etc/otelcol-contrib/config.yaml"
    )


def _ensure_parent_dirs(*paths: Path) -> None:
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, str | None]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prompt_index(label: str, max_value: int) -> int:
    while True:
        choice = click.prompt(label, prompt_suffix=": ", show_default=False).strip().lower()
        if choice.isdigit():
            number = int(choice)
            if 1 <= number <= max_value:
                return number
        click.echo("  Invalid choice.")


def _print_snippet(lines: list[str]) -> None:
    for line in lines:
        click.echo(f"    {line}")
