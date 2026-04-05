"""pai billing report — fetch and display API billing data."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

import click
from rich.text import Text

from ..common.formatting import (
    console,
    fmt_tokens,
    make_table,
    provider_style,
    spinner_status,
    truncate,
)
from .pricing import compute_cost, load_pricing
from .providers import ALL_PROVIDERS, get_providers

_PROVIDER_CHOICES = ALL_PROVIDERS


def _parse_last(value: str) -> tuple[datetime, datetime]:
    m = re.fullmatch(r"(\d+)([dmw])", value.strip())
    if not m:
        raise click.BadParameter(f"invalid format {value!r}, use e.g. 7d, 2w, 30d")
    n, unit = int(m.group(1)), m.group(2)
    end = datetime.now()
    if unit == "m":
        start = end - timedelta(minutes=n)
    elif unit == "d":
        start = end - timedelta(days=n)
    else:
        start = end - timedelta(weeks=n)
    return start, end


def _parse_date(value: str) -> datetime:
    from dateutil import parser as dp

    try:
        return dp.parse(value, fuzzy=True)
    except Exception:
        raise click.BadParameter(f"cannot parse date: {value!r}")


def _aggregate(rows: list[tuple], dim: str) -> list[tuple]:
    buckets: dict[tuple, list] = {}
    for provider, model, month, in_tok, out_tok, cost in rows:
        if dim == "provider":
            key = (provider, "—", "—")
        elif dim == "model":
            key = (provider, model, "—")
        elif dim == "month":
            key = ("—", "—", month)
        else:
            key = (provider, model, month)
        if key not in buckets:
            buckets[key] = [0, 0, 0.0]
        buckets[key][0] += in_tok
        buckets[key][1] += out_tok
        buckets[key][2] += cost
    return [(k[0], k[1], k[2], int(v[0]), int(v[1]), v[2]) for k, v in buckets.items()]


@click.command("report")
@click.option(
    "--provider",
    "-p",
    multiple=True,
    type=click.Choice(_PROVIDER_CHOICES, case_sensitive=False),
    help="Provider(s) to include (repeatable). Default: openai + anthropic.",
)
@click.option("--last", metavar="DURATION", help="Relative window: 7d, 2w, 30d.")
@click.option("--from", "from_date", metavar="DATE", help="Start date (flexible format).")
@click.option("--to", "to_date", metavar="DATE", help="End date (flexible format). Default: now.")
@click.option(
    "--aggr",
    type=click.Choice(["provider", "model", "month"], case_sensitive=False),
    metavar="DIM",
    help="Aggregate by: provider, model, or month.",
)
def report_cmd(
    provider: tuple[str, ...],
    last: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str],
    aggr: Optional[str],
) -> None:
    """Fetch and display API billing data."""
    if last:
        start, end = _parse_last(last)
    else:
        start = _parse_date(from_date) if from_date else datetime.now() - timedelta(days=30)
        end = _parse_date(to_date) if to_date else datetime.now()

    selected = list(provider) if provider else ["openai", "anthropic"]
    providers = get_providers(selected)

    unavailable = []
    available = []
    for p in providers:
        ok, reason = p.is_available()
        if ok:
            available.append(p)
        else:
            unavailable.append((p.name, reason))

    for name, reason in unavailable:
        console.print(
            Text.assemble(
                ("  Skipping ", "yellow"),
                (name, f"bold {provider_style(name)}"),
                (f": {reason}", "yellow"),
            )
        )

    if not available:
        console.print("[red]No providers available.[/red]")
        return

    pricing = load_pricing()
    rows: list[tuple] = []

    for p in available:
        with spinner_status(p.name):
            records = p.fetch(start, end)
        for rec in records:
            cost = compute_cost(rec, pricing)
            rows.append((rec.provider, rec.model, rec.month, rec.input_tokens, rec.output_tokens, cost))

    if not rows:
        console.print("[yellow]No billing data found.[/yellow]")
        return

    if aggr:
        rows = _aggregate(rows, aggr)

    rows.sort(key=lambda r: (r[0], r[2], r[1]))
    table = make_table("Provider", "Model", "Month", "In Tokens", "Out Tokens", "Cost (USD)")

    total_cost = 0.0
    provider_totals: dict[str, float] = {}
    current_provider: Optional[str] = None

    for provider_name, model, month, in_tok, out_tok, cost in rows:
        if current_provider and provider_name != current_provider:
            table.add_section()
            table.add_row(
                Text(f"Subtotal: {current_provider}", style=f"bold {provider_style(current_provider)}"),
                "", "", "", "",
                Text(f"${provider_totals[current_provider]:.4f}", style=f"bold {provider_style(current_provider)}"),
            )
            table.add_section()

        current_provider = provider_name
        provider_totals[provider_name] = provider_totals.get(provider_name, 0.0) + cost
        total_cost += cost

        table.add_row(
            Text(provider_name, style=f"bold {provider_style(provider_name)}"),
            truncate(model, 44),
            month,
            fmt_tokens(in_tok),
            fmt_tokens(out_tok),
            f"${cost:.4f}",
        )

    if len(provider_totals) > 1 and current_provider:
        table.add_section()
        table.add_row(
            Text(f"Subtotal: {current_provider}", style=f"bold {provider_style(current_provider)}"),
            "", "", "", "",
            Text(f"${provider_totals[current_provider]:.4f}", style=f"bold {provider_style(current_provider)}"),
        )

    table.add_section()
    table.add_row(
        Text("TOTAL", style="bold"),
        "", "", "", "",
        Text(f"${total_cost:.4f}", style="bold"),
    )

    console.print()
    console.print(table)
