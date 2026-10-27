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


def test_overview_breakdowns_preserve_missing_zero_and_filtered_population(projection):
    store, warehouse = projection
    one = purchase("one", orgaoEntidadeRazaoSocial="Saúde", modalidadeNome="Pregão eletrônico",
                   valorTotalHomologado=0)
    one["valorTotalEstimado"] = 0
    two = purchase("two", orgaoEntidadeRazaoSocial="Educação", modalidadeNome="Dispensa")
    two["valorTotalEstimado"] = None
    two["dataPublicacaoPncp"] = "2026-03-10"
    land(warehouse, "pncp_contratacao", [one, two])
    land(warehouse, "licitacao", [dict(id_compra="legacy", codigoMunicipioIbge=4202909,
                                     data_publicacao="2025-12-10", valor_estimado_total=300)])
    build_snapshot(store, "4202909")
    data = overview(store, "4202909", {})
    assert data["metrics"]["purchases"] == 3
    assert data["metrics"]["estimated_known"] == 2
    assert data["metrics"]["awarded_known"] == 1
    assert data["metrics"]["organizations"] == 2  # unknown is not an organization
    assert data["metrics"]["organization_known"] == data["metrics"]["modality_known"] == 2
    assert data["sources"] == [{"family": "legacy", "purchases": 1}, {"family": "pncp", "purchases": 2}]
    assert [r["month"] for r in data["monthly"]] == ["2025-12", "2026-01", "2026-03"]
    assert data["monthly"][1]["estimated"] == data["monthly"][1]["awarded"] == 0
    assert data["monthly"][2]["estimated"] is None
    assert data["monthly"][2]["estimated_known"] == 0
    assert sum(r["purchases"] for r in data["modality_breakdown"]) == 3
    assert sum(r["purchases"] for r in data["organizations"]) == 3
    assert data["date_range"] == data["filtered_range"]

    for selected in ({"modality": "Pregão eletrônico"}, {"org_name": "Saúde"},
                     {"start_date": "2026-01-01", "end_date": "2026-01-31"}, {"q": "Compra one"}):
        filtered = overview(store, "4202909", selected)
        assert filtered["metrics"]["purchases"] == 1
        assert filtered["metrics"]["estimated"] == filtered["metrics"]["awarded"] == 0
        assert filtered["modality_breakdown"][0]["modality"] == "Pregão eletrônico"
        assert filtered["organizations"][0]["org_name"] == "Saúde"
        assert filtered["sources"] == [{"family": "pncp", "purchases": 1}]
        assert str(filtered["filtered_range"]["start_date"]) == "2026-01-10"
        assert str(filtered["date_range"]["start_date"]) == "2025-12-10"
        assert len(filtered["modalities"]) == 3  # filter choices remain global


def test_overview_empty_has_no_fabricated_amounts_or_groups(projection):
    store, warehouse = projection
    land(warehouse, "pncp_contratacao", [purchase("one")])
    build_snapshot(store, "4202909")
    data = overview(store, "4202909", {"q": "no match"})
    assert data["metrics"]["purchases"] == 0
    assert data["metrics"]["estimated"] is data["metrics"]["awarded"] is None
    assert data["metrics"]["organization_known"] == data["metrics"]["modality_known"] == 0
    assert data["monthly"] == data["organizations"] == data["modality_breakdown"] == data["sources"] == []
    assert data["filtered_range"] == {"start_date": None, "end_date": None}
    assert data["coverage"]["status"] == "unverified"


def test_value_ranking_keeps_organizations_outside_volume_top_eight(projection):
    store, warehouse = projection
    records = [purchase(f"small-{org}-{i}", orgaoEntidadeRazaoSocial=f"Órgão {org}",
                        valorTotalHomologado=10) for org in range(9) for i in range(2)]
    records.append(purchase("large", orgaoEntidadeRazaoSocial="Grande valor", valorTotalHomologado=1000000))
    land(warehouse, "pncp_contratacao", records)
    build_snapshot(store, "4202909")
    data = overview(store, "4202909", {})
    assert len(data["organizations"]) == 10
    assert max(data["organizations"], key=lambda r: r["awarded"])["org_name"] == "Grande valor"
    assert sum(r["purchases"] for r in data["organizations"]) == 19


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
