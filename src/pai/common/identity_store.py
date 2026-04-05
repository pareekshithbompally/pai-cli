"""SQLite-backed identity state under XDG data paths."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .paths import app_data_path

DB_PATH = app_data_path("pai.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS identity_events (
    agent          TEXT NOT NULL,
    session_id     TEXT NOT NULL,
    identity_value TEXT NOT NULL,
    identity_kind  TEXT NOT NULL,
    source         TEXT NOT NULL,
    first_seen_at  TEXT,
    last_seen_at   TEXT,
    PRIMARY KEY (agent, session_id, identity_value, source)
);
CREATE TABLE IF NOT EXISTS identity_aliases (
    agent      TEXT NOT NULL,
    raw_value  TEXT NOT NULL,
    label      TEXT NOT NULL,
    updated_at TEXT,
    PRIMARY KEY (agent, raw_value)
);
CREATE TABLE IF NOT EXISTS identity_ingestion_offsets (
    agent       TEXT NOT NULL,
    source_path TEXT NOT NULL,
    offset      INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT,
    PRIMARY KEY (agent, source_path)
);
CREATE TABLE IF NOT EXISTS identity_setup_state (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_identity_events_agent_session
    ON identity_events (agent, session_id);
"""


class IdentityStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def commit(self) -> None:
        self._conn.commit()

    def set_alias(self, agent: str, raw_value: str, label: str, updated_at: str | None = None, *, commit: bool = True) -> None:
        self._conn.execute(
            """
            INSERT INTO identity_aliases (agent, raw_value, label, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(agent, raw_value) DO UPDATE SET
                label = excluded.label,
                updated_at = excluded.updated_at
            """,
            (agent, raw_value, label, updated_at),
        )
        if commit:
            self._conn.commit()

    def list_aliases(self, agent: str | None = None) -> list[sqlite3.Row]:
        if agent is None:
            return self._conn.execute(
                "SELECT agent, raw_value, label, updated_at FROM identity_aliases ORDER BY agent, raw_value"
            ).fetchall()
        return self._conn.execute(
            """
            SELECT agent, raw_value, label, updated_at
            FROM identity_aliases
            WHERE agent = ?
            ORDER BY raw_value
            """,
            (agent,),
        ).fetchall()

    def get_alias_map(self, agent: str | None = None) -> dict[tuple[str, str], str]:
        return {
            (row["agent"], row["raw_value"]): row["label"]
            for row in self.list_aliases(agent)
        }

    def remove_alias(self, agent: str, raw_value: str) -> int:
        cur = self._conn.execute(
            """
            DELETE FROM identity_aliases
            WHERE agent = ? AND raw_value = ?
            """,
            (agent, raw_value),
        )
        self._conn.commit()
        return cur.rowcount

    def clear_identity_data(
        self,
        agent: str | None = None,
        *,
        include_aliases: bool = False,
        include_setup: bool = False,
    ) -> dict[str, int]:
        counts = {
            "events": 0,
            "offsets": 0,
            "aliases": 0,
            "setup": 0,
        }

        if agent is None:
            counts["events"] = self._conn.execute("DELETE FROM identity_events").rowcount
            counts["offsets"] = self._conn.execute("DELETE FROM identity_ingestion_offsets").rowcount
            counts["setup"] = self._conn.execute(
                "DELETE FROM identity_setup_state WHERE key LIKE 'identity.%.last_ingest_at'"
            ).rowcount
            if include_aliases:
                counts["aliases"] = self._conn.execute("DELETE FROM identity_aliases").rowcount
            if include_setup:
                counts["setup"] += self._conn.execute("DELETE FROM identity_setup_state").rowcount
        else:
            counts["events"] = self._conn.execute(
                "DELETE FROM identity_events WHERE agent = ?",
                (agent,),
            ).rowcount
            counts["offsets"] = self._conn.execute(
                "DELETE FROM identity_ingestion_offsets WHERE agent = ?",
                (agent,),
            ).rowcount
            counts["setup"] = self._conn.execute(
                "DELETE FROM identity_setup_state WHERE key = ?",
                (f"identity.{agent}.last_ingest_at",),
            ).rowcount
            if include_aliases:
                counts["aliases"] = self._conn.execute(
                    "DELETE FROM identity_aliases WHERE agent = ?",
                    (agent,),
                ).rowcount
            if include_setup:
                counts["setup"] += self._conn.execute(
                    "DELETE FROM identity_setup_state WHERE key LIKE ?",
                    (f"identity.{agent}.%",),
                ).rowcount

        self._conn.commit()
        return counts

    def upsert_identity_event(
        self,
        agent: str,
        session_id: str,
        identity_value: str,
        identity_kind: str,
        source: str,
        *,
        seen_at: str | None = None,
        commit: bool = True,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO identity_events (
                agent, session_id, identity_value, identity_kind, source, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent, session_id, identity_value, source) DO UPDATE SET
                identity_kind = excluded.identity_kind,
                first_seen_at = COALESCE(identity_events.first_seen_at, excluded.first_seen_at),
                last_seen_at = excluded.last_seen_at
            """,
            (agent, session_id, identity_value, identity_kind, source, seen_at, seen_at),
        )
        if commit:
            self._conn.commit()

    def latest_identities(self, agent: str | None = None) -> list[sqlite3.Row]:
        if agent is None:
            rows = self._conn.execute(
                """
                SELECT agent, session_id, identity_value, identity_kind, source, first_seen_at, last_seen_at
                FROM identity_events
                ORDER BY agent, session_id, COALESCE(last_seen_at, first_seen_at, '') DESC
                """
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT agent, session_id, identity_value, identity_kind, source, first_seen_at, last_seen_at
                FROM identity_events
                WHERE agent = ?
                ORDER BY session_id, COALESCE(last_seen_at, first_seen_at, '') DESC
                """,
                (agent,),
            ).fetchall()

        latest: dict[tuple[str, str], sqlite3.Row] = {}
        for row in rows:
            key = (row["agent"], row["session_id"])
            latest.setdefault(key, row)
        return list(latest.values())

    def set_offset(self, agent: str, source_path: str, offset: int, updated_at: str | None = None, *, commit: bool = True) -> None:
        self._conn.execute(
            """
            INSERT INTO identity_ingestion_offsets (agent, source_path, offset, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(agent, source_path) DO UPDATE SET
                offset = excluded.offset,
                updated_at = excluded.updated_at
            """,
            (agent, source_path, offset, updated_at),
        )
        if commit:
            self._conn.commit()

    def get_offset(self, agent: str, source_path: str) -> int:
        row = self._conn.execute(
            """
            SELECT offset
            FROM identity_ingestion_offsets
            WHERE agent = ? AND source_path = ?
            """,
            (agent, source_path),
        ).fetchone()
        return int(row["offset"]) if row else 0

    def get_offsets(self, agent: str | None = None) -> list[sqlite3.Row]:
        if agent is None:
            return self._conn.execute(
                "SELECT agent, source_path, offset, updated_at FROM identity_ingestion_offsets ORDER BY agent, source_path"
            ).fetchall()
        return self._conn.execute(
            """
            SELECT agent, source_path, offset, updated_at
            FROM identity_ingestion_offsets
            WHERE agent = ?
            ORDER BY source_path
            """,
            (agent,),
        ).fetchall()

    def set_setup_value(self, key: str, value: str | None, updated_at: str | None = None, *, commit: bool = True) -> None:
        self._conn.execute(
            """
            INSERT INTO identity_setup_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, updated_at),
        )
        if commit:
            self._conn.commit()

    def get_setup_state(self) -> dict[str, str | None]:
        rows = self._conn.execute("SELECT key, value FROM identity_setup_state ORDER BY key").fetchall()
        return {row["key"]: row["value"] for row in rows}
