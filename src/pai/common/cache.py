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

from .identity_store import IdentityStore
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
    identity_value  TEXT    NOT NULL DEFAULT '—',
    identity_kind   TEXT    NOT NULL DEFAULT 'none',
    identity_source TEXT    NOT NULL DEFAULT 'none',
    identity_label  TEXT,
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
        _ensure_schema(self._conn)
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

    def apply_identity_overrides(self, agents: Optional[list[str]] = None) -> int:
        store = IdentityStore()
        try:
            rows = []
            if agents:
                for agent in agents:
                    rows.extend(store.latest_identities(agent))
                alias_map = {}
                for agent in agents:
                    alias_map.update(store.get_alias_map(agent))
            else:
                rows = store.latest_identities()
                alias_map = store.get_alias_map()
        finally:
            store.close()

        updated = 0
        for row in rows:
            identity_value = row["identity_value"]
            identity_label = alias_map.get((row["agent"], identity_value))
            cur = self._conn.execute(
                """
                UPDATE sessions
                SET identity_value = ?,
                    identity_kind = ?,
                    identity_source = ?,
                    identity_label = ?,
                    account = COALESCE(?, ?)
                WHERE agent = ? AND session_id = ?
                """,
                (
                    identity_value,
                    row["identity_kind"],
                    row["source"],
                    identity_label,
                    identity_label,
                    identity_value,
                    row["agent"],
                    row["session_id"],
                ),
            )
            updated += cur.rowcount

        if agents:
            placeholders = ",".join("?" * len(agents))
            session_rows = self._conn.execute(
                f"SELECT file_path, agent, identity_value FROM sessions WHERE agent IN ({placeholders})",
                agents,
            ).fetchall()
        else:
            session_rows = self._conn.execute(
                "SELECT file_path, agent, identity_value FROM sessions"
            ).fetchall()

        for row in session_rows:
            identity_label = alias_map.get((row["agent"], row["identity_value"]))
            cur = self._conn.execute(
                """
                UPDATE sessions
                SET identity_label = ?,
                    account = COALESCE(?, identity_value)
                WHERE file_path = ?
                """,
                (identity_label, identity_label, row["file_path"]),
            )
            updated += cur.rowcount
        if updated:
            self._conn.commit()
        return updated

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
                 session_id, account,
                 identity_value, identity_kind, identity_source, identity_label,
                 project,
                 msg_count, first_ts, last_ts,
                 in_tokens, out_tokens)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(file_path) DO UPDATE SET
                file_mtime  = excluded.file_mtime,
                file_size   = excluded.file_size,
                session_id  = excluded.session_id,
                account     = excluded.account,
                identity_value  = excluded.identity_value,
                identity_kind   = excluded.identity_kind,
                identity_source = excluded.identity_source,
                identity_label  = excluded.identity_label,
                project     = excluded.project,
                msg_count   = excluded.msg_count,
                first_ts    = excluded.first_ts,
                last_ts     = excluded.last_ts,
                in_tokens   = excluded.in_tokens,
                out_tokens  = excluded.out_tokens
            """,
            (
                agent, str(path), mtime, size,
                rec.session_id, rec.account,
                rec.identity_value, rec.identity_kind, rec.identity_source, rec.identity_label,
                rec.project,
                rec.msg_count, rec.first_ts, rec.last_ts,
                rec.in_tokens, rec.out_tokens,
            ),
        )


def _row_to_record(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        agent      = row["agent"],
        file_path  = row["file_path"],
        session_id = row["session_id"],
        project    = row["project"],
        msg_count  = row["msg_count"],
        first_ts   = row["first_ts"],
        last_ts    = row["last_ts"],
        in_tokens  = row["in_tokens"],
        out_tokens = row["out_tokens"],
        identity_value  = row["identity_value"],
        identity_kind   = row["identity_kind"],
        identity_source = row["identity_source"],
        identity_label  = row["identity_label"],
    )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(sessions)")
    }

    migrations = {
        "identity_value": "ALTER TABLE sessions ADD COLUMN identity_value TEXT NOT NULL DEFAULT '—'",
        "identity_kind": "ALTER TABLE sessions ADD COLUMN identity_kind TEXT NOT NULL DEFAULT 'none'",
        "identity_source": "ALTER TABLE sessions ADD COLUMN identity_source TEXT NOT NULL DEFAULT 'none'",
        "identity_label": "ALTER TABLE sessions ADD COLUMN identity_label TEXT",
    }
    for column, sql in migrations.items():
        if column not in existing:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

    conn.execute("CREATE INDEX IF NOT EXISTS idx_identity_value ON sessions (identity_value)")

    conn.execute(
        """
        UPDATE sessions
        SET identity_value = COALESCE(NULLIF(account, ''), '—')
        WHERE COALESCE(identity_value, '') = ''
        """
    )
