"""Bounded, read-only access to project documentation and collected data."""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

import duckdb

from .manifest import build_historical_manifest, build_operation_catalog, default_date_window


DOCUMENTS = {"readme": "README.md", "api-reference": "docs/API_COMPRAS_GOV.md"}
WAREHOUSE_TABLES = ("bronze_pages", "silver_records")
OPS_TABLES = ("ops_runs", "ops_checkpoints", "ops_errors")


def _validate_page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if offset < 0:
        raise ValueError("offset must be non-negative")


def _page(rows: list[dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
    return {
        "items": rows[:limit],
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if len(rows) > limit else None,
    }


def _rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    return [
        {
            key: value.isoformat() if isinstance(value, (date, datetime)) else value
            for key, value in zip(columns, row)
        }
        for row in cursor.fetchall()
    ]


def _record(row: dict[str, Any]) -> dict[str, Any]:
    return {**{key: value for key, value in row.items() if key != "payload_json"}, "payload": json.loads(row["payload_json"])}


class ProjectAccess:
    def __init__(
        self,
        db_path: str | Path = "compras.duckdb",
        ops_db_path: str | Path | None = None,
        project_root: str | Path | None = None,
    ):
        self.db_path = Path(db_path).expanduser().resolve()
        self.ops_db_path = (
            Path(ops_db_path).expanduser().resolve()
            if ops_db_path is not None
            else self.db_path.with_name(f"{self.db_path.stem}_ops.sqlite")
        )
        self.project_root = Path(project_root or Path.cwd()).expanduser().resolve()

    def _duck_rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if not self.db_path.is_file():
            raise FileNotFoundError("DuckDB warehouse not found. Run compras-crawler sync first or configure --db-path.")
        try:
            with duckdb.connect(str(self.db_path), read_only=True) as con:
                return _rows(con.execute(sql, params))
        except duckdb.Error as exc:
            raise ValueError(
                "Cannot read the DuckDB warehouse. Check its schema and stop any sync writing to this file "
                "before retrying (or use a snapshot)."
            ) from exc

    def _ops_rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if not self.ops_db_path.is_file():
            raise FileNotFoundError("SQLite operations database not found. Run compras-crawler sync first or configure --ops-db-path.")
        try:
            # A sqlite connection context alone does not close the connection.
            with closing(sqlite3.connect(f"{self.ops_db_path.as_uri()}?mode=ro", uri=True)) as con:
                return _rows(con.execute(sql, params))
        except sqlite3.Error as exc:
            raise ValueError("Cannot read the SQLite operations database. Check --ops-db-path and its schema.") from exc

    def _document_path(self, document: str) -> Path:
        if document not in DOCUMENTS:
            raise ValueError(f"Unknown document. Choose one of: {', '.join(DOCUMENTS)}")
        candidate = self.project_root / DOCUMENTS[document]
        path = candidate.resolve()
        if path != candidate or not path.is_relative_to(self.project_root):
            raise ValueError("Document must stay inside --project-root and must not use symlinks")
        return path

    def document_text(self, document: str) -> str:
        path = self._document_path(document)
        if not path.is_file():
            raise FileNotFoundError("Project document not found. Set --project-root to the repository directory.")
        return path.read_text(encoding="utf-8")

    def project_info(self) -> dict[str, Any]:
        return {
            "name": "compras-crawler",
            "description": "Compras.gov.br public procurement crawler: raw pages and normalized records in DuckDB; sync metadata in SQLite.",
            "read_only": True,
            "documents": [{"id": key, "path": path} for key, path in DOCUMENTS.items()],
            "warehouse": {"path": str(self.db_path), "exists": self.db_path.is_file(), "tables": list(WAREHOUSE_TABLES)},
            "operations": {"path": str(self.ops_db_path), "exists": self.ops_db_path.is_file(), "tables": list(OPS_TABLES)},
        }

    def read_document(self, document: str, start_line: int = 1, line_count: int = 120) -> dict[str, Any]:
        if start_line < 1 or not 1 <= line_count <= 200:
            raise ValueError("start_line must be positive and line_count must be between 1 and 200")
        lines = self.document_text(document).splitlines()
        end = start_line - 1 + line_count
        return {
            "document": document,
            "start_line": start_line,
            "total_lines": len(lines),
            "text": "\n".join(lines[start_line - 1:end]),
            "next_line": end + 1 if end < len(lines) else None,
        }

    def list_operations(self) -> list[dict[str, Any]]:
        # One representative PNCP job includes this optional operation in the
        # catalog; no request or default-modality recommendation is made here.
        jobs = build_historical_manifest(*default_date_window(), pncp_modalidade_codes=(1,))
        return [
            {
                "operation_id": spec.operation_id,
                "entity_name": spec.entity_name,
                "path": spec.path,
                "accepts": list(spec.accepts),
                "requires_pncp_modalidade_code": spec.operation_id == "consultarContratacoes_PNCP_14133",
            }
            for spec in build_operation_catalog(jobs)
        ]

    def database_schema(self) -> dict[str, Any]:
        # Identifiers are fixed constants, never agent-supplied SQL.
        return {
            "warehouse": {table: self._duck_rows(f"PRAGMA table_info('{table}')") for table in WAREHOUSE_TABLES},
            "operations": {table: self._ops_rows(f"PRAGMA table_info('{table}')") for table in OPS_TABLES},
        }

    def list_entities(self) -> list[dict[str, Any]]:
        return self._duck_rows(
            "SELECT entity_name, count(*) AS record_count, max(last_seen_at) AS last_seen_at "
            "FROM silver_records GROUP BY entity_name ORDER BY entity_name"
        )

    def search_records(
        self, entity_name: str, query: str | None = None, limit: int = 20, offset: int = 0,
    ) -> dict[str, Any]:
        _validate_page(limit, offset)
        rows = self._duck_rows(
            "SELECT * FROM silver_records WHERE entity_name = ? "
            "AND (? IS NULL OR contains(lower(payload_json), lower(?))) "
            "ORDER BY record_key LIMIT ? OFFSET ?",
            (entity_name, query, query, limit + 1, offset),
        )
        result = _page(rows, limit, offset)
        result["items"] = [_record(row) for row in result["items"]]
        return result

    def get_record(self, entity_name: str, record_key: str) -> dict[str, Any]:
        rows = self._duck_rows(
            "SELECT * FROM silver_records WHERE entity_name = ? AND record_key = ?",
            (entity_name, record_key),
        )
        return {"record": _record(rows[0]) if rows else None}

    def list_sync_runs(self, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        _validate_page(limit, offset)
        return _page(self._ops_rows(
            "SELECT * FROM ops_runs ORDER BY started_at DESC, run_id DESC LIMIT ? OFFSET ?",
            (limit + 1, offset),
        ), limit, offset)

    def list_checkpoints(self, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        _validate_page(limit, offset)
        return _page(self._ops_rows(
            "SELECT * FROM ops_checkpoints ORDER BY job_name LIMIT ? OFFSET ?",
            (limit + 1, offset),
        ), limit, offset)

    def list_sync_errors(self, run_id: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        _validate_page(limit, offset)
        return _page(self._ops_rows(
            "SELECT run_id, job_name, page_number, message, created_at FROM ops_errors "
            "WHERE (? IS NULL OR run_id = ?) ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (run_id, run_id, limit + 1, offset),
        ), limit, offset)
