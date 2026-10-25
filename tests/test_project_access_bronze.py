import pytest

from compras_crawler.crawl_state import CrawlState
from compras_crawler.normalize import stable_hash, stable_json
from compras_crawler.project_access import ProjectAccess
from compras_crawler.storage import BronzeWarehouse, SqliteOpsStore


@pytest.fixture
def bronze(tmp_path):
    warehouse = BronzeWarehouse(tmp_path / "bronze.duckdb")
    warehouse.init_schema()
    ops = SqliteOpsStore(tmp_path / "ops.sqlite")
    ops.init_schema()
    return warehouse, ProjectAccess(warehouse.db_path, ops.db_path, tmp_path)


def land(warehouse, entity, payload, page=1, content_type="json"):
    warehouse.land_page(run_id=f"run-{page}", job_name=f"job-{entity}", entity_name=entity,
                        page_number=page, request_params_json="{}", response_format=content_type,
                        http_status=200, payload_json=stable_json(payload),
                        payload_text=payload if isinstance(payload, str) else None,
                        payload_hash=stable_hash(payload))


def test_bronze_reads_keep_observations_and_csv_without_creating_silver(bronze):
    warehouse, access = bronze
    land(warehouse, "uasg", [{"codigoUasg": 1, "nomeUasg": "São Paulo"}])
    land(warehouse, "uasg", {"resultado": [{"codigoUasg": 1, "nomeUasg": "São Paulo"}]}, page=2)
    land(warehouse, "price", "codigo,descricao\n1,Papel\n", content_type="text/csv")
    land(warehouse, "empty", {"resultado": []})
    before = warehouse.db_path.read_bytes()
    entities = {row["entity_name"]: row for row in access.list_entities()}
    assert entities["uasg"]["record_count"] == 2
    assert entities["uasg"]["page_count"] == 2
    assert entities["empty"]["record_count"] == 0
    assert entities["empty"]["page_count"] == 1
    found = access.search_records("uasg", limit=1)
    assert found["storage"] == "bronze" and found["next_offset"] == 1
    first = found["items"][0]
    second = access.search_records("uasg", offset=1)["items"][0]
    assert first["payload"] == second["payload"]
    assert first["record_key"] != second["record_key"]
    assert first["payload_hash"] == stable_hash(first["payload"])
    assert first["page_payload_hash"]
    assert second["source_page"] == 2
    assert access.get_record("uasg", second["record_key"])["record"] == second
    assert access.get_record("price", second["record_key"])["record"] is None
    csv_row = access.search_records("price", query="PAPEL")["items"][0]
    assert csv_row["payload"] == {"codigo": "1", "descricao": "Papel"}
    assert set(access.database_schema()["warehouse"]) == {"bronze_pages"}
    assert warehouse.db_path.read_bytes() == before


@pytest.mark.parametrize("key", ["missing", "0:-1", "-1:0", "0:9999", "0:0:0",
    "0:١", f"{2**63}:0", "9" * 5000 + ":0"])
def test_invalid_bronze_keys_do_not_query_other_records(bronze, key):
    warehouse, access = bronze
    land(warehouse, "uasg", [{"codigoUasg": 1}])
    assert access.get_record("uasg", key) == {"record": None}


@pytest.mark.parametrize("wrapper", [None, "resultado", "records", "items", "data"])
def test_supported_raw_wrappers_are_read_without_materializing_tables(bronze, wrapper):
    warehouse, access = bronze
    rows = [{"id": "one"}, {"id": "two"}]
    land(warehouse, "test", rows if wrapper is None else {wrapper: rows})
    result = access.search_records("test")
    assert [row["payload"] for row in result["items"]] == rows


def test_full_city_checkpoint_table_is_optional_but_visible_when_present(bronze):
    warehouse, access = bronze
    CrawlState(warehouse).init_schema()
    assert set(access.database_schema()["warehouse"]) == {"bronze_pages", "bronze_crawl_jobs"}
