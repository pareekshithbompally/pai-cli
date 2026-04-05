"""pai billing — API cost reporting for OpenAI, Anthropic, and Google Cloud."""

from __future__ import annotations

import click

from .pricing_cmd import pricing_cmd
from .report import report_cmd


@click.group("billing", help="API cost reporting (OpenAI, Anthropic, Google).")
def billing_group() -> None:
    pass


billing_group.add_command(report_cmd)
billing_group.add_command(pricing_cmd)
