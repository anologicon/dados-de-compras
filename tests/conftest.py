from __future__ import annotations

from pathlib import Path

import pytest

from compras_crawler.normalize import normalize_records
from compras_crawler.project_access import ProjectAccess
from compras_crawler.storage import DuckWarehouse, SqliteOpsStore


@pytest.fixture
def project_access(tmp_path: Path) -> ProjectAccess:
    root = tmp_path / "project"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("# Compras\nContexto do projeto\nTerceira linha\n", encoding="utf-8")
    (root / "docs" / "API_COMPRAS_GOV.md").write_text("# API\nReferência pública\n", encoding="utf-8")
    data_path = tmp_path / "data.duckdb"
    # Exercise URI encoding for SQLite filenames.
    ops_path = tmp_path / "ops #metadata?.sqlite"
    warehouse = DuckWarehouse(data_path)
    ops = SqliteOpsStore(ops_path)
    warehouse.init_schema()
    ops.init_schema()
    run_id = ops.start_run(base_url="https://dadosabertos.compras.gov.br", scope="test", data_db_path=data_path)
    warehouse.upsert_records(normalize_records(
        entity_name="uasg",
        records=[
            {"codigoUasg": 1, "nomeUasg": "São Paulo", "objeto": "Desconto 10%"},
            {"codigoUasg": 2, "nomeUasg": "Brasília"},
            {"codigoUasg": 3, "nomeUasg": "Outra unidade"},
        ],
        key_fields=("codigoUasg",), run_id=run_id, source_job="uasg_true", source_page=1,
    ))
    warehouse.upsert_records(normalize_records(
        entity_name="material_item", records=[{"codigoItem": 1, "descricao": "Papel"}],
        key_fields=("codigoItem",), run_id=run_id, source_job="material_item_true", source_page=2,
    ))
    ops.save_checkpoint("uasg_true", next_page=2)
    ops.save_checkpoint("material_item_true", next_page=3)
    ops.record_error(run_id=run_id, job_name="uasg_true", page_number=2, message="API unavailable", payload_json=None)
    ops.finish_run(run_id, status="failed")
    return ProjectAccess(data_path, ops_path, root)
