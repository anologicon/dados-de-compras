from __future__ import annotations

import json
from pathlib import Path

import pytest

from compras_crawler.project_access import ProjectAccess


def test_project_info_and_docs_work_without_databases(tmp_path: Path):
    access = ProjectAccess(tmp_path / "not-created" / "data.duckdb", project_root=tmp_path)
    info = access.project_info()
    assert info["read_only"] is True
    assert info["warehouse"]["exists"] is False
    assert access.ops_db_path == tmp_path / "not-created" / "data_ops.sqlite"
    assert {item["operation_id"] for item in access.list_operations()} >= {
        "consultarUasg", "consultarLicitacao", "consultarContratacoes_PNCP_14133",
    }
    with pytest.raises(FileNotFoundError, match="--project-root"):
        access.read_document("readme")
    with pytest.raises(FileNotFoundError, match="--db-path"):
        access.list_entities()
    with pytest.raises(FileNotFoundError, match="--ops-db-path"):
        access.list_sync_runs()
    assert not (tmp_path / "not-created").exists()


def test_document_pagination_and_allowlist(project_access: ProjectAccess, tmp_path: Path):
    page = project_access.read_document("readme", line_count=2)
    assert page["text"] == "# Compras\nContexto do projeto"
    assert page["total_lines"] == 3
    assert page["next_line"] == 3
    assert project_access.read_document("readme", start_line=3)["next_line"] is None
    assert project_access.read_document("readme", start_line=50)["text"] == ""
    assert "pública" in project_access.document_text("api-reference")
    for name in (".env", "../README.md", "/etc/passwd"):
        with pytest.raises(ValueError, match="Unknown document"):
            project_access.read_document(name)

    outside = tmp_path / "secret.txt"
    outside.write_text("not for agents", encoding="utf-8")
    readme = project_access.project_root / "README.md"
    readme.unlink()
    readme.symlink_to(outside)
    with pytest.raises(ValueError, match="inside --project-root"):
        project_access.document_text("readme")
    readme.unlink()
    secret = project_access.project_root / ".env"
    secret.write_text("COMPRAS_GOV_TOKEN=secret", encoding="utf-8")
    readme.symlink_to(secret)
    with pytest.raises(ValueError, match="must not use symlinks"):
        project_access.document_text("readme")


@pytest.mark.parametrize("start_line,line_count", [(0, 10), (1, 0), (1, 201)])
def test_document_invalid_bounds(project_access: ProjectAccess, start_line: int, line_count: int):
    with pytest.raises(ValueError):
        project_access.read_document("readme", start_line, line_count)


def test_schema_and_entities(project_access: ProjectAccess, warehouse_format: str):
    schema = project_access.database_schema()
    expected = {"bronze_pages", "silver_records"} if warehouse_format == "legacy" else {"bronze_pages"}
    assert set(schema["warehouse"]) == expected
    assert set(schema["operations"]) == {"ops_runs", "ops_checkpoints", "ops_errors"}
    assert "payload_json" in {column["name"] for column in schema["warehouse"]["bronze_pages"]}
    entities = project_access.list_entities()
    assert [(row["entity_name"], row["record_count"]) for row in entities] == [("material_item", 1), ("uasg", 3)]
    assert isinstance(entities[0]["last_seen_at"], str)
    json.dumps(schema)


def test_record_search_pagination_and_provenance(project_access: ProjectAccess, warehouse_format: str):
    first = project_access.search_records("uasg", limit=2)
    assert first["storage"] == ("legacy_silver" if warehouse_format == "legacy" else "bronze")
    assert [row["payload"]["codigoUasg"] for row in first["items"]] == [1, 2]
    assert first["next_offset"] == 2
    last = project_access.search_records("uasg", limit=2, offset=first["next_offset"])
    assert [row["payload"]["codigoUasg"] for row in last["items"]] == [3]
    assert last["next_offset"] is None
    assert project_access.search_records("uasg", offset=50)["items"] == []
    row = project_access.search_records("uasg", query="PAULO")["items"][0]
    assert row["payload"]["nomeUasg"] == "São Paulo"
    assert row["source_job"] == "uasg_true"
    assert row["source_page"] == 1
    assert row["run_id"]
    assert "payload_json" not in row
    assert project_access.get_record("uasg", row["record_key"])["record"] == row
    assert project_access.get_record("uasg", "missing") == {"record": None}
    assert project_access.search_records("missing")["items"] == []
    # Wildcards are literal text, not LIKE patterns.
    assert len(project_access.search_records("uasg", query="%")["items"]) == 1
    json.dumps(first)


def test_queries_are_parameterized(project_access: ProjectAccess):
    injection = "' OR 1=1; DROP TABLE silver_records; --"
    assert project_access.search_records(injection)["items"] == []
    assert project_access.search_records("uasg", query=injection)["items"] == []
    assert project_access.get_record("uasg", injection) == {"record": None}
    assert project_access.list_sync_errors(run_id=injection)["items"] == []
    assert len(project_access.search_records("uasg")["items"]) == 3


def test_sync_metadata_and_read_only_files(project_access: ProjectAccess):
    paths = (project_access.db_path, project_access.ops_db_path)
    before = {path: path.read_bytes() for path in paths}
    run = project_access.list_sync_runs()["items"][0]
    assert run["status"] == "failed"
    checkpoints = project_access.list_checkpoints(limit=1)
    assert checkpoints["items"][0]["next_page"] == 3
    assert checkpoints["next_offset"] == 1
    assert project_access.list_checkpoints(offset=1)["items"][0]["job_name"] == "uasg_true"
    errors = project_access.list_sync_errors(run_id=run["run_id"])
    assert errors["items"][0]["message"] == "API unavailable"
    assert project_access.list_sync_errors(run_id="unknown")["items"] == []
    project_access.database_schema()
    project_access.search_records("uasg")
    for path in paths:
        assert path.read_bytes() == before[path]


@pytest.mark.parametrize("method", ["search_records", "list_sync_runs", "list_checkpoints", "list_sync_errors"])
@pytest.mark.parametrize("limit,offset", [(0, 0), (101, 0), (1, -1)])
def test_invalid_page_bounds(project_access: ProjectAccess, method: str, limit: int, offset: int):
    args = ("uasg",) if method == "search_records" else ()
    with pytest.raises(ValueError):
        getattr(project_access, method)(*args, limit=limit, offset=offset)


def test_existing_invalid_databases_report_actionable_errors(tmp_path: Path):
    db = tmp_path / "invalid.duckdb"
    db.write_text("not duckdb", encoding="utf-8")
    ops = tmp_path / "invalid.sqlite"
    ops.write_text("not sqlite", encoding="utf-8")
    access = ProjectAccess(db, ops)
    with pytest.raises(ValueError, match="Cannot read the DuckDB"):
        access.list_entities()
    with pytest.raises(ValueError, match="Cannot read the SQLite"):
        access.list_sync_runs()
