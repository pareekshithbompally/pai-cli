"""pai billing pricing — show or refresh the LiteLLM pricing cache."""

from __future__ import annotations

import click

from ..common.formatting import console, make_table, spinner_status, truncate
from .pricing import load_pricing, pricing_cache_path, pricing_last_updated, refresh_pricing


@click.command("pricing")
@click.option("--refresh", is_flag=True, help="Fetch latest pricing from LiteLLM before displaying.")
def pricing_cmd(refresh: bool) -> None:
    """Show cached API pricing tables (per 1M tokens, USD)."""
    if refresh:
        with spinner_status("pricing from LiteLLM"):
            cache = refresh_pricing()
    else:
        cache = load_pricing()

    console.print(f"[dim]  Cache: {pricing_cache_path()}  |  Last updated: {pricing_last_updated(cache)}[/dim]")
    console.print()

    openai_data = cache.get("openai", {})
    anthropic_data = cache.get("anthropic", {})

    if openai_data:
        table = make_table("Model", "Input", "Output", "Cached", title="OpenAI Pricing (per 1M tokens, USD)")
        for model, p in sorted(openai_data.items()):
            table.add_row(
                truncate(model, 44),
                f"${p.get('input',  0):.3f}",
                f"${p.get('output', 0):.3f}",
                f"${p.get('cached', 0):.3f}",
            )
        console.print(table)
        console.print()

    if anthropic_data:
        table = make_table(
            "Model", "Input", "Output", "Cache Read", "Cache Write 5m", "Cache Write 1h",
            title="Anthropic Pricing (per 1M tokens, USD)",
        )
        for model, p in sorted(anthropic_data.items()):
            table.add_row(
                truncate(model, 44),
                f"${p.get('input',          0):.3f}",
                f"${p.get('output',         0):.3f}",
                f"${p.get('cache_read',     0):.3f}",
                f"${p.get('cache_write_5m', 0):.3f}",
                f"${p.get('cache_write_1h', 0):.3f}",
            )
        console.print(table)

    if not openai_data and not anthropic_data:
        console.print("[yellow]Pricing cache is empty. Run with --refresh to populate it.[/yellow]")
