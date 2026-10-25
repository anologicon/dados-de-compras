import hashlib
import json

import pytest

from compras_crawler.normalize import stable_hash, stable_json
from compras_crawler.storage import BronzeWarehouse
from compras_crawler.web.analytics import build_snapshot, export_purchases, overview, purchases
from compras_crawler.web.seed import import_seed
from compras_crawler.web.store import AppStore


@pytest.fixture
def projection(tmp_path):
    store = AppStore(tmp_path / "managed")
    store.init_schema()
    store.add_city("4202909", "Brusque", "SC")
    warehouse = BronzeWarehouse(store.city_dir("4202909") / "bronze.duckdb")
    warehouse.init_schema()
    return store, warehouse


def land(warehouse, entity, rows, run="first"):
    payload = {"resultado": rows, "totalPaginas": 1}
    warehouse.land_page(run_id=run, job_name=entity, entity_name=entity, page_number=1,
                        request_params_json='{}', response_format="json", http_status=200,
                        payload_json=stable_json(payload), payload_text=None, payload_hash=stable_hash(payload))


def purchase(key, **extra):
    return dict(idCompra=key, numeroControlePNCP="control-" + key, unidadeOrgaoCodigoIbge=4202909,
                unidadeOrgaoCodigoUnidade="1", dataPublicacaoPncp="2026-01-10", objetoCompra="Compra " + key,
                valorTotalEstimado=100, **extra)


def test_projection_deduplicates_and_preserves_unknown_values(projection):
    store, warehouse = projection
    land(warehouse, "pncp_contratacao", [purchase("one"), purchase("two")])
    land(warehouse, "pncp_contratacao_id", [purchase("one")], run="second")
    land(warehouse, "licitacao", [dict(id_compra="one", co_uasg="1", data_publicacao="2026-01-10", valor_estimado_total=999)])
    land(warehouse, "uasg", [dict(codigoUasg="1", codigoMunicipioIbge=4202909)])
    land(warehouse, "licitacao_id", [dict(objeto="sem identidade", data_publicacao="2026-01-10")])
    wrong_city = purchase("elsewhere")
    wrong_city["unidadeOrgaoCodigoIbge"] = 4205407
    land(warehouse, "pncp_contratacao", [wrong_city], run="third")
    summary = build_snapshot(store, "4202909")
    data = overview(store, "4202909", {})
    assert data["metrics"]["purchases"] == 2
    assert data["metrics"]["estimated"] == 200
    assert data["metrics"]["awarded"] is None
    assert summary["status"] == "unverified"
    assert summary["unreconciled"] == 1
    assert purchases(store, "4202909", {"q": "' OR 1=1 --"}, 1, 25)["total"] == 0


def test_deleted_authoritative_purchase_does_not_resurrect_legacy(projection):
    store, warehouse = projection
    land(warehouse, "pncp_contratacao", [purchase("one")])
    land(warehouse, "pncp_contratacao_id", [dict(idCompra="one", contratacaoExcluida=True, dataAtualizacaoPncp="2026-08-24")], run="new")
    land(warehouse, "licitacao", [dict(id_compra="one", codigoMunicipioIbge=4202909, data_publicacao="2026-01-10")])
    build_snapshot(store, "4202909")
    assert overview(store, "4202909", {})["metrics"]["purchases"] == 0


def test_conflicting_official_identifiers_not_consolidated(projection):
    store, warehouse = projection
    one, two = purchase("one"), purchase("two")
    two["numeroControlePNCP"] = one["numeroControlePNCP"]
    land(warehouse, "pncp_contratacao", [one, two])
    summary = build_snapshot(store, "4202909")
    assert overview(store, "4202909", {})["metrics"]["purchases"] == 0
    assert summary["unreconciled"] == 2


def test_exports_include_whole_filtered_set_and_originals(projection):
    store, warehouse = projection
    records = [purchase(str(i)) for i in range(35)]
    records[0]["objetoCompra"] = "=1+1"
    land(warehouse, "pncp_contratacao", records)
    build_snapshot(store, "4202909")
    assert len(purchases(store, "4202909", {}, 1, 25)["items"]) == 25
    exported = json.loads("".join(export_purchases(store, "4202909", {}, "json")))
    assert len(exported["records"]) == 35
    assert exported["records"][0]["original"]
    csv = "".join(export_purchases(store, "4202909", {}, "csv"))
    assert "'=1+1" in csv
    assert "snapshot_built_at" in csv
    assert len(json.loads("".join(export_purchases(store, "4202909", {"q": "Compra 34"}, "json")))["records"]) == 1


def test_fenced_projection_cannot_replace_current_snapshot(projection):
    store, warehouse = projection
    land(warehouse, "pncp_contratacao", [purchase("one")])
    build_snapshot(store, "4202909")
    previous = store.city("4202909")["snapshot"]
    def revoked():
        raise RuntimeError("lease revoked")
    with pytest.raises(RuntimeError, match="lease revoked"):
        build_snapshot(store, "4202909", before_publish=revoked)
    assert store.city("4202909")["snapshot"] == previous
    assert (store.root / previous).exists()


def test_empty_successful_page_can_publish_an_empty_snapshot(projection):
    store, warehouse = projection
    land(warehouse, "pncp_contratacao", [])
    build_snapshot(store, "4202909")
    assert overview(store, "4202909", {})["metrics"]["purchases"] == 0


def test_snapshot_retains_current_and_previous(projection):
    store, warehouse = projection
    land(warehouse, "pncp_contratacao", [purchase("one")])
    paths = []
    for _ in range(3):
        build_snapshot(store, "4202909")
        paths.append(store.root / store.city("4202909")["snapshot"])
    assert not paths[0].exists()
    assert all(p.exists() for p in paths[1:])


def test_seed_preserves_source_and_refuses_overwrite(tmp_path):
    source = tmp_path / "original.duckdb"
    warehouse = BronzeWarehouse(source)
    warehouse.init_schema()
    land(warehouse, "pncp_contratacao", [purchase("one")])
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    store = AppStore(tmp_path / "workspace")
    result = import_seed(store, source, "4202909", "Brusque", "SC")
    assert result["bronze_pages"] == 1
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    with pytest.raises(FileExistsError):
        import_seed(store, source, "4202909", "Brusque", "SC")
