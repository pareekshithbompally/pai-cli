"""Cache sync helper used by commands that need fresh data."""

from __future__ import annotations

from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from ..agents import get_adapters
from ..common.cache import SessionCache
from ..common.identity_ingest import ingest_identity_telemetry


def ensure_synced(cache: SessionCache, agents: list[str], *, force: bool = False) -> None:
    """Sync cache for the given agents, showing a progress bar if work is needed."""
    adapters = get_adapters(agents)
    ingest_identity_telemetry(agents)

    # Quick pre-check: count files needing parse without doing it
    total_to_parse = 0
    for adapter in adapters:
        disk_files  = adapter.discover_files()
        disk_index  = {}
        for p in disk_files:
            try:
                st = p.stat()
                disk_index[str(p)] = (st.st_mtime, st.st_size)
            except OSError:
                continue

        if force:
            total_to_parse += len(disk_index)
            continue

        cached = {
            row["file_path"]: (row["file_mtime"], row["file_size"])
            for row in cache._conn.execute(
                "SELECT file_path, file_mtime, file_size FROM sessions WHERE agent = ?",
                (adapter.name,),
            )
        }
        for path_str, (mtime, size) in disk_index.items():
            c = cached.get(path_str)
            if c is None or c[0] != mtime or c[1] != size:
                total_to_parse += 1

    if total_to_parse == 0:
        cache.apply_identity_overrides(agents)
        return  # All cached — silent fast path

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(f"Syncing {total_to_parse} sessions…", total=total_to_parse)

        def cb(done: int, total: int, path: str) -> None:
            progress.update(task, completed=done)

        for adapter in adapters:
            cache.sync(adapter, force=force, progress_callback=cb)
    cache.apply_identity_overrides(agents)
