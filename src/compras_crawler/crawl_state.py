"""Atomic page/checkpoint persistence for full-city crawls.

The SQLite ops checkpoint is informational. Resume is based on state committed
in the *same DuckDB transaction* as the raw page, so a crash between databases
cannot skip a page. Historical Bronze pages are never removed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import uuid

from .normalize import extract_records, stable_hash, stable_json
from .storage import BronzeWarehouse


class CrawlStopped(Exception):
    """Cooperative stop, not an endpoint failure."""


class CrawlState:
    def __init__(self, warehouse: BronzeWarehouse):
        self.warehouse = warehouse

    def init_schema(self) -> None:
        with self.warehouse.connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS bronze_crawl_jobs (
                    job_key TEXT PRIMARY KEY, job_name TEXT, generation TEXT,
                    next_page INTEGER, complete BOOLEAN
                )
            """)

    def open_job(self, key: str, name: str, *, resume: bool) -> dict[str, Any]:
        with self.warehouse.connect() as con:
            row = con.execute(
                "SELECT generation, next_page, complete FROM bronze_crawl_jobs WHERE job_key = ?", [key]
            ).fetchone()
            if row and resume:
                return dict(generation=row[0], next_page=row[1], complete=row[2])
            generation = str(uuid.uuid4())
            con.execute(
                "INSERT OR REPLACE INTO bronze_crawl_jobs VALUES (?, ?, ?, 1, false)",
                [key, name, generation],
            )
            return dict(generation=generation, next_page=1, complete=False)

    def load_pages(self, key: str, name: str, generation: str) -> list[tuple[int, Any, str]]:
        with self.warehouse.connect() as con:
            rows = con.execute("""
                SELECT page_number, payload_json, payload_hash FROM bronze_pages
                WHERE job_name = ?
                  AND json_extract_string(request_params_json, '$._crawl_key') = ?
                  AND json_extract_string(request_params_json, '$._crawl_generation') = ?
                ORDER BY page_number
            """, [name, key, generation]).fetchall()
        return [(page, json.loads(payload), digest) for page, payload, digest in rows]

    def commit_page(self, *, key: str, generation: str, job_name: str, entity_name: str,
                    run_id: str, page: Any, complete: bool, auth_used: bool) -> None:
        params = dict(page.params, _auth_used=auth_used, _crawl_key=key, _crawl_generation=generation)
        with self.warehouse.connect() as con:
            con.execute("BEGIN TRANSACTION")
            try:
                # The next-page guard also makes a replay after a lost acknowledgement harmless.
                state = con.execute(
                    "SELECT next_page, generation FROM bronze_crawl_jobs WHERE job_key = ?", [key]
                ).fetchone()
                if state is None or state[1] != generation:
                    raise RuntimeError("crawl generation changed while writing")
                if page.page_number < state[0]:
                    con.execute("ROLLBACK")
                    return
                if page.page_number != state[0]:
                    raise RuntimeError("non-contiguous crawl page")
                con.execute("INSERT INTO bronze_pages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                    run_id, job_name, entity_name, page.page_number, stable_json(params),
                    page.content_type or "json", page.status_code, stable_json(page.raw),
                    page.raw if isinstance(page.raw, str) else None, stable_hash(page.raw),
                    datetime.now(timezone.utc),
                ])
                con.execute("UPDATE bronze_crawl_jobs SET next_page = ?, complete = ? WHERE job_key = ?",
                            [page.page_number + 1, complete, key])
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise

    @staticmethod
    def records(pages: list[tuple[int, Any, str]]) -> list[dict[str, Any]]:
        return [record for _, payload, _ in pages for record in extract_records(payload)]
