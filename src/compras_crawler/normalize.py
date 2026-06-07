from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def extract_records(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("resultado", "records", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def first_present(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def normalize_record(
    *,
    entity_name: str,
    record: dict[str, Any],
    key_fields: tuple[str, ...],
    run_id: str,
    source_job: str,
    source_page: int,
    fetched_at: datetime | None = None,
) -> dict[str, Any]:
    fetched_at = fetched_at or datetime.now(tz=timezone.utc)
    record_key = first_present(record, key_fields)
    if record_key is None:
        record_key = stable_hash(record)
    return {
        "entity_name": entity_name,
        "record_key": str(record_key),
        "payload_json": stable_json(record),
        "payload_hash": stable_hash(record),
        "run_id": run_id,
        "source_job": source_job,
        "source_page": source_page,
        "fetched_at": fetched_at,
    }


def normalize_records(
    *,
    entity_name: str,
    records: list[dict[str, Any]],
    key_fields: tuple[str, ...],
    run_id: str,
    source_job: str,
    source_page: int,
    fetched_at: datetime | None = None,
) -> list[dict[str, Any]]:
    return [
        normalize_record(
            entity_name=entity_name,
            record=record,
            key_fields=key_fields,
            run_id=run_id,
            source_job=source_job,
            source_page=source_page,
            fetched_at=fetched_at,
        )
        for record in records
    ]
