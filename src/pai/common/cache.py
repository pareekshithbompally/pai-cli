"""SQLite-backed session cache with mtime+size change detection.

On each sync():
  1. Discover all session files on disk (fast glob via adapter).
  2. Stat each file (mtime, size) — no reads.
  3. Compare against cached rows:
       - New/modified → parse and upsert.
       - Deleted      → remove from cache.
       - Unchanged    → skip entirely.
  4. Query cache for commands.

Cache lives under XDG_CACHE_HOME/pai/sessions.db.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .paths import app_cache_path
from .types import SessionRecord

if TYPE_CHECKING:
    from ..agents.base import AgentAdapter  # noqa: F401

CACHE_PATH = app_cache_path("sessions.db")
CACHE_DIR = CACHE_PATH.parent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    agent       TEXT    NOT NULL,
    file_path   TEXT    NOT NULL PRIMARY KEY,
    file_mtime  REAL    NOT NULL,
    file_size   INTEGER NOT NULL,
    session_id  TEXT    NOT NULL,
    account     TEXT    NOT NULL,
    project     TEXT    NOT NULL,
    msg_count   INTEGER NOT NULL DEFAULT 0,
    first_ts    TEXT,
    last_ts     TEXT,
    in_tokens   INTEGER NOT NULL DEFAULT 0,
    out_tokens  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_agent    ON sessions (agent);
CREATE INDEX IF NOT EXISTS idx_last_ts  ON sessions (last_ts);
CREATE INDEX IF NOT EXISTS idx_account  ON sessions (account);
"""


class SessionCache:
    def __init__(self, db_path: Path = CACHE_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── Sync ─────────────────────────────────────────────────────────────────

    def sync(
        self,
        adapter: "AgentAdapter",
        *,
        force: bool = False,
        progress_callback=None,
    ) -> tuple[int, int, int]:
        """Sync cache for one agent. Returns (parsed, skipped, deleted)."""
        agent = adapter.name

        disk_files = adapter.discover_files()
        disk_index = {}
        for p in disk_files:
            try:
                st = p.stat()
                disk_index[str(p)] = (st.st_mtime, st.st_size)
            except OSError:
                continue

        # Load cached rows for this agent
        cached: dict[str, tuple[float, int]] = {
            row["file_path"]: (row["file_mtime"], row["file_size"])
            for row in self._conn.execute(
                "SELECT file_path, file_mtime, file_size FROM sessions WHERE agent = ?",
                (agent,),
            )
        }

        # Deleted files
        deleted_paths = set(cached) - set(disk_index)
        if deleted_paths:
            self._conn.executemany(
                "DELETE FROM sessions WHERE file_path = ?",
                [(p,) for p in deleted_paths],
            )

        # Files to parse (new or changed)
        to_parse: list[Path] = []
        for path_str, (mtime, size) in disk_index.items():
            c = cached.get(path_str)
            if force or c is None or c[0] != mtime or c[1] != size:
                to_parse.append(Path(path_str))

        skipped = len(disk_index) - len(to_parse)

        for i, path in enumerate(to_parse):
            if progress_callback:
                progress_callback(i + 1, len(to_parse), str(path))
            try:
                rec = adapter.parse_session(path)
                mtime, size = disk_index[str(path)]
                if rec is not None and rec.msg_count > 0:
                    self._upsert(agent, path, mtime, size, rec)
                else:
                    # Empty/unreadable session — remove stale cache entry if present
                    self._conn.execute(
                        "DELETE FROM sessions WHERE file_path = ?", (str(path),)
                    )
            except Exception:
                pass  # Never crash on a single bad file

        self._conn.commit()
        return len(to_parse), skipped, len(deleted_paths)

    # ── Query ─────────────────────────────────────────────────────────────────

    def query(
        self,
        agents: Optional[list[str]] = None,
        account_filter: Optional[str] = None,
        project_filter: Optional[str] = None,
    ) -> list[SessionRecord]:
        """Return all matching sessions, sorted by last_ts desc."""
        wheres = []
        params: list = []

        if agents:
            placeholders = ",".join("?" * len(agents))
            wheres.append(f"agent IN ({placeholders})")
            params.extend(agents)
        if account_filter:
            wheres.append("LOWER(account) LIKE ?")
            params.append(f"%{account_filter.lower()}%")
        if project_filter:
            wheres.append("LOWER(project) LIKE ?")
            params.append(f"%{project_filter.lower()}%")

        where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        sql = f"""
            SELECT * FROM sessions
            {where_clause}
            ORDER BY last_ts DESC NULLS LAST
        """
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_record(r) for r in rows]

    def clear(self, agent: Optional[str] = None) -> int:
        if agent:
            cur = self._conn.execute("DELETE FROM sessions WHERE agent = ?", (agent,))
        else:
            cur = self._conn.execute("DELETE FROM sessions")
        self._conn.commit()
        return cur.rowcount

    def stats_summary(self) -> list[dict]:
        """Quick per-agent row counts for diagnostics."""
        rows = self._conn.execute(
            "SELECT agent, COUNT(*) as cnt FROM sessions GROUP BY agent ORDER BY agent"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _upsert(
        self,
        agent: str,
        path: Path,
        mtime: float,
        size: int,
        rec: SessionRecord,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO sessions
                (agent, file_path, file_mtime, file_size,
                 session_id, account, project,
                 msg_count, first_ts, last_ts,
                 in_tokens, out_tokens)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(file_path) DO UPDATE SET
                file_mtime  = excluded.file_mtime,
                file_size   = excluded.file_size,
                session_id  = excluded.session_id,
                account     = excluded.account,
                project     = excluded.project,
                msg_count   = excluded.msg_count,
                first_ts    = excluded.first_ts,
                last_ts     = excluded.last_ts,
                in_tokens   = excluded.in_tokens,
                out_tokens  = excluded.out_tokens
            """,
            (
                agent, str(path), mtime, size,
                rec.session_id, rec.account, rec.project,
                rec.msg_count, rec.first_ts, rec.last_ts,
                rec.in_tokens, rec.out_tokens,
            ),
        )


def _row_to_record(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        agent      = row["agent"],
        file_path  = row["file_path"],
        session_id = row["session_id"],
        account    = row["account"],
        project    = row["project"],
        msg_count  = row["msg_count"],
        first_ts   = row["first_ts"],
        last_ts    = row["last_ts"],
        in_tokens  = row["in_tokens"],
        out_tokens = row["out_tokens"],
    )
