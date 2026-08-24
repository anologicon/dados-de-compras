from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid

import duckdb


DEFAULT_DB_PREFIX = Path("dados_abertos_compras")


def _base_prefix_path(base_path: str | Path) -> Path:
    path = Path(base_path)
    if path.suffix == ".duckdb":
        return path.with_suffix("")
    return path


def derive_bronze_db_path(base_path: str | Path) -> Path:
    """Derive the Bronze DuckDB path from a user-facing base path.

    Examples:
    - dados_abertos_compras -> dados_abertos_compras_bronze.duckdb
    - compras.duckdb -> compras_bronze.duckdb
    """

    prefix = _base_prefix_path(base_path)
    return prefix.with_name(f"{prefix.name}_bronze.duckdb")


def derive_ops_db_path(base_path: str | Path) -> Path:
    prefix = _base_prefix_path(base_path)
    return prefix.with_name(f"{prefix.name}_ops.sqlite")


class BronzeWarehouse:
    """Bronze-only DuckDB warehouse for raw fetched API pages."""

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


# Backward-compatible public name used by older callers/tests.
DuckWarehouse = BronzeWarehouse


@dataclass(frozen=True)
class BronzeMigrationResult:
    source_db_path: Path
    bronze_db_path: Path
    bronze_pages: int


def migrate_bronze_database(
    *,
    source_db_path: str | Path,
    bronze_db_path: str | Path,
    overwrite: bool = False,
) -> BronzeMigrationResult:
    """Copy the legacy single-DuckDB ``bronze_pages`` table into a Bronze DB."""

    source = Path(source_db_path)
    bronze = Path(bronze_db_path)
    if not source.exists():
        raise FileNotFoundError(source)
    if bronze.resolve() == source.resolve():
        raise ValueError("target bronze DB path must be different from the source DB")
    if bronze.exists():
        if not overwrite:
            raise FileExistsError(bronze)
        bronze.unlink()

    BronzeWarehouse(bronze).init_schema()
    bronze_count = _copy_table_from_source(source, bronze, "bronze_pages")
    return BronzeMigrationResult(
        source_db_path=source,
        bronze_db_path=bronze,
        bronze_pages=bronze_count,
    )


def _copy_table_from_source(source_db_path: Path, target_db_path: Path, table_name: str) -> int:
    source_literal = str(source_db_path).replace("'", "''")
    with duckdb.connect(str(target_db_path)) as con:
        con.execute(f"ATTACH '{source_literal}' AS source (READ_ONLY)")
        exists = con.execute(
            """
            SELECT count(*)
            FROM duckdb_tables()
            WHERE database_name = 'source'
              AND schema_name = 'main'
              AND table_name = ?
            """,
            [table_name],
        ).fetchone()[0]
        if not exists:
            return 0
        con.execute(f"INSERT INTO {table_name} SELECT * FROM source.main.{table_name}")
        return int(con.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0])


class SqliteOpsStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(self.db_path))

    def init_schema(self) -> None:
        with self.connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ops_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT,
                    finished_at TEXT,
                    status TEXT,
                    base_url TEXT,
                    data_db_path TEXT,
                    bronze_db_path TEXT,
                    ops_db_path TEXT,
                    scope TEXT
                )
                """
            )
            self._ensure_ops_runs_columns(con)
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS ops_checkpoints (
                    job_name TEXT PRIMARY KEY,
                    next_page INTEGER,
                    payload_hash TEXT,
                    updated_at TEXT
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
                    created_at TEXT
                )
                """
            )

    def _ensure_ops_runs_columns(self, con: sqlite3.Connection) -> None:
        existing = {row[1] for row in con.execute("PRAGMA table_info(ops_runs)").fetchall()}
        required = {
            "data_db_path": "TEXT",
            "bronze_db_path": "TEXT",
            "ops_db_path": "TEXT",
            "scope": "TEXT",
        }
        for column, column_type in required.items():
            if column not in existing:
                con.execute(f"ALTER TABLE ops_runs ADD COLUMN {column} {column_type}")

    def start_run(
        self,
        *,
        base_url: str,
        scope: str,
        data_db_path: str | Path | None = None,
        bronze_db_path: str | Path | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        started_at = datetime.now(tz=timezone.utc).isoformat()
        data_path = str(Path(data_db_path)) if data_db_path is not None else None
        bronze_path = str(Path(bronze_db_path)) if bronze_db_path is not None else None
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO ops_runs (
                    run_id, started_at, finished_at, status, base_url, data_db_path,
                    bronze_db_path, ops_db_path, scope
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
                """,
                [run_id, started_at, "running", base_url, data_path, bronze_path, str(self.db_path), scope],
            )
        return run_id

    def finish_run(self, run_id: str, *, status: str) -> None:
        finished_at = datetime.now(tz=timezone.utc).isoformat()
        with self.connect() as con:
            con.execute(
                "UPDATE ops_runs SET finished_at = ?, status = ? WHERE run_id = ?",
                [finished_at, status, run_id],
            )

    def save_checkpoint(self, job_name: str, *, next_page: int, payload_hash: str | None = None) -> None:
        updated_at = datetime.now(tz=timezone.utc).isoformat()
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
        created_at = datetime.now(tz=timezone.utc).isoformat()
        with self.connect() as con:
            con.execute(
                "INSERT INTO ops_errors VALUES (?, ?, ?, ?, ?, ?)",
                [run_id, job_name, page_number, message, payload_json, created_at],
            )
