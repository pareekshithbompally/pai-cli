#!/usr/bin/env python3
"""
pai — Session, billing, cache, and diagnostics CLI for AI agent workflows.

Usage:
  pai sessions <command> [options]
  pai billing  <command> [options]
  pai cache    <command> [options]
  pai identity <command> [options]
  pai setup    <command> [options]
  pai doctor

Examples:
  pai sessions history --agent claude
  pai sessions stats --agent copilot
  pai sessions messages ~/.claude/projects/.../abc123.jsonl
  pai sessions plans --agent codex
  pai identity alias set --agent claude tech@tatvacare.in Work
  pai identity clear --agent claude
  pai setup identity
  pai billing report --provider openai
  pai cache info
  pai doctor
"""

from __future__ import annotations

import click

from .billing import billing_group
from .commands import cache_group, doctor_cmd, identity_group, sessions_group, setup_group

@click.group()
def cli() -> None:
    """Unified observability CLI for AI coding agents."""


cli.add_command(sessions_group)
cli.add_command(cache_group)
cli.add_command(identity_group)
cli.add_command(billing_group)
cli.add_command(setup_group)
cli.add_command(doctor_cmd)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
