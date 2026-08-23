from __future__ import annotations

from pathlib import Path

from compras_crawler.storage import DuckWarehouse, SqliteOpsStore


def test_storage_separates_data_and_ops(tmp_path: Path):
    data_db_path = tmp_path / "compras.duckdb"
    ops_db_path = tmp_path / "compras_ops.sqlite"
    warehouse = DuckWarehouse(data_db_path)
    ops = SqliteOpsStore(ops_db_path)
    warehouse.init_schema()
    ops.init_schema()

    run_id = ops.start_run(base_url="https://dadosabertos.compras.gov.br", scope="historical", data_db_path=data_db_path)
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
    warehouse.upsert_records(
        [
            {
                "entity_name": "uasg",
                "record_key": "1",
                "payload_json": '{"codigoUasg": 1, "nomeUasg": "A"}',
                "payload_hash": "row-hash-1",
                "run_id": run_id,
                "source_job": "uasg_status_true",
                "source_page": 1,
            }
        ]
    )
    ops.save_checkpoint("uasg_status_true", next_page=2, payload_hash="hash-1")
    ops.finish_run(run_id, status="finished")

    assert ops.load_checkpoint("uasg_status_true") == 2
    with warehouse.connect() as con:
        assert con.execute("select count(*) from bronze_pages").fetchone()[0] == 1
        assert con.execute("select count(*) from silver_records").fetchone()[0] == 1
    with ops.connect() as con:
        assert con.execute("select status from ops_runs where run_id = ?", [run_id]).fetchone()[0] == "finished"
        assert con.execute("select count(*) from ops_checkpoints").fetchone()[0] == 1

    warehouse.upsert_records(
        [
            {
                "entity_name": "uasg",
                "record_key": "1",
                "payload_json": '{"codigoUasg": 1, "nomeUasg": "B"}',
                "payload_hash": "row-hash-2",
                "run_id": run_id,
                "source_job": "uasg_status_true",
                "source_page": 2,
            }
        ]
    )

    with warehouse.connect() as con:
        assert con.execute("select payload_json from silver_records where record_key = '1'").fetchone()[0] == '{"codigoUasg": 1, "nomeUasg": "B"}'
