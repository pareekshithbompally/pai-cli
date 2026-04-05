"""Incremental telemetry ingestion for identity-backed agents."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .identity_config import (
    identity_raw_path,
    legacy_identity_raw_paths,
    legacy_identity_session_map_path,
    load_identity_agent_config,
)
from .identity_store import IdentityStore

_PARTIAL = object()
_SUPPORTED_AGENTS = {"claude", "gemini"}


def ingest_identity_telemetry(agents: list[str]) -> dict[str, int]:
    targets = [agent for agent in agents if agent in _SUPPORTED_AGENTS]
    if not targets:
        return {}

    store = IdentityStore()
    try:
        return {
            agent: _ingest_agent(store, agent)
            for agent in targets
        }
    finally:
        store.close()


def _ingest_agent(store: IdentityStore, agent: str) -> int:
    config = load_identity_agent_config(agent)
    primary_source_path = Path(config.get("raw_path") or identity_raw_path(agent))
    primary_source_path.parent.mkdir(parents=True, exist_ok=True)

    updated_at = _now_iso()
    ingested = 0
    seen_paths: set[Path] = set()

    for source_path in (primary_source_path, *legacy_identity_raw_paths(agent)):
        if source_path in seen_paths:
            continue
        seen_paths.add(source_path)
        ingested += _ingest_jsonl_source(
            store,
            agent,
            source_path,
            source_name=f"{agent}-telemetry",
            updated_at=updated_at,
        )

    session_map_path = legacy_identity_session_map_path(agent)
    if session_map_path is not None:
        ingested += _ingest_legacy_session_map(store, agent, session_map_path, updated_at=updated_at)

    if ingested:
        store.set_setup_value(f"identity.{agent}.last_ingest_at", updated_at, updated_at=updated_at, commit=False)
    store.commit()
    return ingested


def _ingest_jsonl_source(
    store: IdentityStore,
    agent: str,
    source_path: Path,
    *,
    source_name: str,
    updated_at: str,
) -> int:
    if not source_path.exists():
        return 0

    file_size = source_path.stat().st_size
    offset = store.get_offset(agent, str(source_path))
    if offset > file_size:
        offset = 0

    ingested = 0
    current_offset = offset
    with source_path.open("rb") as handle:
        handle.seek(offset)
        while True:
            start_offset = handle.tell()
            raw_line = handle.readline()
            if not raw_line:
                break

            parsed = _parse_json_line(raw_line)
            if parsed is _PARTIAL:
                handle.seek(start_offset)
                break

            current_offset = handle.tell()
            if parsed is None:
                continue

            for session_id, identity_value, seen_at in _extract_identity_events(parsed):
                store.upsert_identity_event(
                    agent,
                    session_id,
                    identity_value,
                    "session_account",
                    source_name,
                    seen_at=seen_at,
                    commit=False,
                )
                ingested += 1

    store.set_offset(agent, str(source_path), current_offset, updated_at=updated_at, commit=False)
    return ingested


def _ingest_legacy_session_map(store: IdentityStore, agent: str, source_path: Path, *, updated_at: str) -> int:
    if not source_path.exists():
        return 0

    file_size = source_path.stat().st_size
    offset = store.get_offset(agent, str(source_path))
    if offset > file_size:
        offset = 0

    ingested = 0
    current_offset = offset
    with source_path.open("rb") as handle:
        handle.seek(offset)
        while True:
            start_offset = handle.tell()
            raw_line = handle.readline()
            if not raw_line:
                break

            parsed = _parse_json_line(raw_line)
            if parsed is _PARTIAL:
                handle.seek(start_offset)
                break

            current_offset = handle.tell()
            if not isinstance(parsed, dict):
                continue

            session_id = str(parsed.get("session_id") or "").strip()
            identity_value = str(parsed.get("email") or "").strip()
            seen_at = str(parsed.get("timestamp") or "").strip() or updated_at
            if not session_id or not identity_value:
                continue

            store.upsert_identity_event(
                agent,
                session_id,
                identity_value,
                "session_account",
                "claude-session-map-legacy",
                seen_at=seen_at,
                commit=False,
            )
            ingested += 1

    store.set_offset(agent, str(source_path), current_offset, updated_at=updated_at, commit=False)
    return ingested


def _parse_json_line(raw_line: bytes) -> dict | None | object:
    try:
        text = raw_line.decode("utf-8")
    except UnicodeDecodeError:
        return None

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _PARTIAL if not raw_line.endswith(b"\n") else None

    return parsed if isinstance(parsed, dict) else None


def _extract_identity_events(payload: dict) -> list[tuple[str, str, str]]:
    events: list[tuple[str, str, str]] = []
    for attrs, seen_at in _iter_attribute_sets(payload):
        session_id = attrs.get("session.id", "").strip()
        identity_value = attrs.get("user.email", "").strip()
        if session_id and identity_value:
            events.append((session_id, identity_value, seen_at))
    return events


def _iter_attribute_sets(payload: dict) -> list[tuple[dict[str, str], str]]:
    resource_logs = payload.get("resourceLogs")
    if isinstance(resource_logs, list):
        return _iter_resource_log_attributes(resource_logs)

    attrs = _attribute_map(payload.get("attributes"))
    if attrs:
        return [(attrs, _extract_seen_at(payload))]
    return []


def _iter_resource_log_attributes(resource_logs: list[object]) -> list[tuple[dict[str, str], str]]:
    rows: list[tuple[dict[str, str], str]] = []
    for resource_log in resource_logs:
        if not isinstance(resource_log, dict):
            continue
        resource_attrs = _attribute_map((resource_log.get("resource") or {}).get("attributes"))
        for scope_log in resource_log.get("scopeLogs", []):
            if not isinstance(scope_log, dict):
                continue
            for log_record in scope_log.get("logRecords", []):
                if not isinstance(log_record, dict):
                    continue
                attrs = dict(resource_attrs)
                attrs.update(_attribute_map(log_record.get("attributes")))
                if attrs:
                    rows.append((attrs, _extract_seen_at(log_record)))
    return rows


def _attribute_map(value: object) -> dict[str, str]:
    if isinstance(value, dict):
        attrs: dict[str, str] = {}
        for key, raw in value.items():
            text = _string_value(raw)
            if text:
                attrs[str(key)] = text
        return attrs

    if isinstance(value, list):
        attrs = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if not isinstance(key, str) or not key:
                continue
            text = _string_value(item.get("value"))
            if text:
                attrs[key] = text
        return attrs

    return {}


def _string_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
            if key in value:
                return _string_value(value[key])
    return ""


def _extract_seen_at(payload: dict) -> str:
    for key in ("timestamp", "time", "timeUnixNano", "observedTimeUnixNano"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            if key.endswith("UnixNano"):
                try:
                    return datetime.fromtimestamp(int(value) / 1_000_000_000, tz=timezone.utc).isoformat()
                except ValueError:
                    continue
            return value
    return _now_iso()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
