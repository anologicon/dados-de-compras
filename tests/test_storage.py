from __future__ import annotations

from pathlib import Path

import duckdb

from compras_crawler.storage import BronzeWarehouse, SqliteOpsStore, migrate_bronze_database


def _table_count(db_path: Path, table_name: str) -> int:
    with duckdb.connect(str(db_path), read_only=True) as con:
        return int(con.execute(f"select count(*) from {table_name}").fetchone()[0])


def test_storage_writes_bronze_and_ops_only(tmp_path: Path):
    bronze_db_path = tmp_path / "compras_bronze.duckdb"
    ops_db_path = tmp_path / "compras_ops.sqlite"
    warehouse = BronzeWarehouse(bronze_db_path)
    ops = SqliteOpsStore(ops_db_path)
    warehouse.init_schema()
    ops.init_schema()

    run_id = ops.start_run(
        base_url="https://dadosabertos.compras.gov.br",
        scope="historical",
        data_db_path=tmp_path / "compras",
        bronze_db_path=bronze_db_path,
    )
    warehouse.land_page(
        run_id=run_id,
        job_name="uasg_status_true",
        entity_name="uasg",
        page_number=1,
        request_params_json='{"pagina": 1}',
        response_format="json",
        http_status=200,
        payload_json='{"resultado": []}',
        payload_text=None,
        payload_hash="hash-1",
    )
    ops.save_checkpoint("uasg_status_true", next_page=2, payload_hash="hash-1")
    ops.finish_run(run_id, status="finished")

    assert ops.load_checkpoint("uasg_status_true") == 2
    assert _table_count(bronze_db_path, "bronze_pages") == 1
    with duckdb.connect(str(bronze_db_path), read_only=True) as con:
        tables = {row[0] for row in con.execute("select table_name from duckdb_tables()").fetchall()}
        assert tables == {"bronze_pages"}
    with ops.connect() as con:
        row = con.execute(
            "select status, bronze_db_path from ops_runs where run_id = ?",
            [run_id],
        ).fetchone()
        assert row == ("finished", str(bronze_db_path))
        assert con.execute("select count(*) from ops_checkpoints").fetchone()[0] == 1


def test_migrate_bronze_database_copies_only_legacy_bronze_pages(tmp_path: Path):
    source_db_path = tmp_path / "compras.duckdb"
    with duckdb.connect(str(source_db_path)) as con:
        con.execute(
            "create table bronze_pages(run_id text, job_name text, entity_name text, page_number integer, request_params_json text, response_format text, http_status integer, payload_json text, payload_text text, payload_hash text, fetched_at timestamp)"
        )
        con.execute(
            "insert into bronze_pages values ('run-1', 'job-1', 'uasg', 1, '{}', 'json', 200, '{}', null, 'hash', current_timestamp)"
        )

    result = migrate_bronze_database(
        source_db_path=source_db_path,
        bronze_db_path=tmp_path / "dados_bronze.duckdb",
    )

    assert result.bronze_pages == 1
    assert _table_count(result.bronze_db_path, "bronze_pages") == 1
    with duckdb.connect(str(result.bronze_db_path), read_only=True) as con:
        tables = {row[0] for row in con.execute("select table_name from duckdb_tables()").fetchall()}
        assert tables == {"bronze_pages"}
