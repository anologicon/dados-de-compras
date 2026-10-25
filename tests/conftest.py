from __future__ import annotations

from pathlib import Path

import pytest

from compras_crawler.normalize import normalize_records, stable_hash, stable_json
from compras_crawler.project_access import ProjectAccess
from compras_crawler.storage import BronzeWarehouse, SqliteOpsStore


@pytest.fixture(params=["bronze", "legacy"])
def warehouse_format(request):
    return request.param


@pytest.fixture
def project_access(tmp_path: Path, warehouse_format: str) -> ProjectAccess:
    root = tmp_path / "project"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("# Compras\nContexto do projeto\nTerceira linha\n", encoding="utf-8")
    (root / "docs" / "API_COMPRAS_GOV.md").write_text("# API\nReferência pública\n", encoding="utf-8")
    data_path = tmp_path / "data.duckdb"
    # Exercise URI encoding for SQLite filenames.
    ops_path = tmp_path / "ops #metadata?.sqlite"
    warehouse = BronzeWarehouse(data_path)
    ops = SqliteOpsStore(ops_path)
    warehouse.init_schema()
    ops.init_schema()
    run_id = ops.start_run(base_url="https://dadosabertos.compras.gov.br", scope="test", data_db_path=data_path)
    datasets = [
        ("uasg", "uasg_true", 1, ("codigoUasg",), [
            {"codigoUasg": 1, "nomeUasg": "São Paulo", "objeto": "Desconto 10%"},
            {"codigoUasg": 2, "nomeUasg": "Brasília"},
            {"codigoUasg": 3, "nomeUasg": "Outra unidade"},
        ]),
        ("material_item", "material_item_true", 2, ("codigoItem",), [
            {"codigoItem": 1, "descricao": "Papel"},
        ]),
    ]
    for entity, job, page, keys, records in datasets:
        payload = {"resultado": records}
        warehouse.land_page(run_id=run_id, job_name=job, entity_name=entity, page_number=page,
                            request_params_json="{}", response_format="json", http_status=200,
                            payload_json=stable_json(payload), payload_text=None, payload_hash=stable_hash(payload))
    if warehouse_format == "legacy":
        # Build an old-format database only in this fixture. Production storage
        # stays Bronze-only; MCP must still support already-existing legacy files.
        with warehouse.connect() as con:
            con.execute("""CREATE TABLE silver_records (
                entity_name TEXT, record_key TEXT, payload_json TEXT, payload_hash TEXT,
                run_id TEXT, source_job TEXT, source_page INTEGER,
                first_seen_at TIMESTAMP, last_seen_at TIMESTAMP,
                PRIMARY KEY(entity_name, record_key))""")
            for entity, job, page, keys, records in datasets:
                for row in normalize_records(entity_name=entity, records=records, key_fields=keys,
                                             run_id=run_id, source_job=job, source_page=page):
                    con.execute("INSERT INTO silver_records VALUES (?,?,?,?,?,?,?,?,?)", [
                        row["entity_name"], row["record_key"], row["payload_json"], row["payload_hash"],
                        row["run_id"], row["source_job"], row["source_page"], row["fetched_at"], row["fetched_at"],
                    ])
    ops.save_checkpoint("uasg_true", next_page=2)
    ops.save_checkpoint("material_item_true", next_page=3)
    ops.record_error(run_id=run_id, job_name="uasg_true", page_number=2, message="API unavailable", payload_json=None)
    ops.finish_run(run_id, status="failed")
    return ProjectAccess(data_path, ops_path, root)
