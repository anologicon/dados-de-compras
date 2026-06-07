from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

import duckdb


class DuckWarehouse:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.db_path))

    def init_schema(self) -> None:
        with self.connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS bronze_pages (
                    run_id TEXT,
                    job_name TEXT,
                    entity_name TEXT,
                    page_number INTEGER,
                    request_params_json TEXT,
                    response_format TEXT,
                    http_status INTEGER,
                    payload_json TEXT,
                    payload_text TEXT,
                    payload_hash TEXT,
                    fetched_at TIMESTAMP
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS silver_records (
                    entity_name TEXT,
                    record_key TEXT,
                    payload_json TEXT,
                    payload_hash TEXT,
                    run_id TEXT,
                    source_job TEXT,
                    source_page INTEGER,
                    first_seen_at TIMESTAMP,
                    last_seen_at TIMESTAMP,
                    PRIMARY KEY (entity_name, record_key)
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ops_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    status TEXT,
                    base_url TEXT,
                    db_path TEXT,
                    scope TEXT
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ops_checkpoints (
                    job_name TEXT PRIMARY KEY,
                    next_page INTEGER,
                    payload_hash TEXT,
                    updated_at TIMESTAMP
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ops_errors (
                    run_id TEXT,
                    job_name TEXT,
                    page_number INTEGER,
                    message TEXT,
                    payload_json TEXT,
                    created_at TIMESTAMP
                )
                """
            )

    def start_run(self, *, base_url: str, scope: str) -> str:
        run_id = str(uuid.uuid4())
        started_at = datetime.now(tz=timezone.utc)
        with self.connect() as con:
            con.execute(
                "INSERT INTO ops_runs (run_id, started_at, finished_at, status, base_url, db_path, scope) VALUES (?, ?, NULL, ?, ?, ?, ?)",
                [run_id, started_at, "running", base_url, str(self.db_path), scope],
            )
        return run_id

    def finish_run(self, run_id: str, *, status: str) -> None:
        finished_at = datetime.now(tz=timezone.utc)
        with self.connect() as con:
            con.execute(
                "UPDATE ops_runs SET finished_at = ?, status = ? WHERE run_id = ?",
                [finished_at, status, run_id],
            )

    def land_page(
        self,
        *,
        run_id: str,
        job_name: str,
        entity_name: str,
        page_number: int,
        request_params_json: str,
        response_format: str,
        http_status: int,
        payload_json: str,
        payload_text: str | None,
        payload_hash: str,
    ) -> None:
        fetched_at = datetime.now(tz=timezone.utc)
        with self.connect() as con:
            con.execute(
                "INSERT INTO bronze_pages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    run_id,
                    job_name,
                    entity_name,
                    page_number,
                    request_params_json,
                    response_format,
                    http_status,
                    payload_json,
                    payload_text,
                    payload_hash,
                    fetched_at,
                ],
            )

    def upsert_records(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        now = datetime.now(tz=timezone.utc)
        with self.connect() as con:
            con.execute("BEGIN TRANSACTION")
            try:
                for row in rows:
                    con.execute(
                        "DELETE FROM silver_records WHERE entity_name = ? AND record_key = ?",
                        [row["entity_name"], row["record_key"]],
                    )
                    con.execute(
                        """
                        INSERT INTO silver_records (
                            entity_name, record_key, payload_json, payload_hash, run_id, source_job, source_page, first_seen_at, last_seen_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            row["entity_name"],
                            row["record_key"],
                            row["payload_json"],
                            row["payload_hash"],
                            row["run_id"],
                            row["source_job"],
                            row["source_page"],
                            row.get("first_seen_at", now),
                            row.get("last_seen_at", now),
                        ],
                    )
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise

    def save_checkpoint(self, job_name: str, *, next_page: int, payload_hash: str | None = None) -> None:
        updated_at = datetime.now(tz=timezone.utc)
        with self.connect() as con:
            con.execute("DELETE FROM ops_checkpoints WHERE job_name = ?", [job_name])
            con.execute(
                "INSERT INTO ops_checkpoints VALUES (?, ?, ?, ?)",
                [job_name, next_page, payload_hash, updated_at],
            )

    def load_checkpoint(self, job_name: str) -> int | None:
        with self.connect() as con:
            row = con.execute("SELECT next_page FROM ops_checkpoints WHERE job_name = ?", [job_name]).fetchone()
            return int(row[0]) if row else None

    def record_error(self, *, run_id: str, job_name: str, page_number: int | None, message: str, payload_json: str | None) -> None:
        created_at = datetime.now(tz=timezone.utc)
        with self.connect() as con:
            con.execute(
                "INSERT INTO ops_errors VALUES (?, ?, ?, ?, ?, ?)",
                [run_id, job_name, page_number, message, payload_json, created_at],
            )
