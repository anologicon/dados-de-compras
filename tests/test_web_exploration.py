import json

import pytest

from compras_crawler.normalize import stable_hash, stable_json
from compras_crawler.storage import BronzeWarehouse
from compras_crawler.web.analytics import build_snapshot, connection
from compras_crawler.web.exploration import (
    SnapshotChanged, document, purchase_detail, purchase_items, purchase_results, supplier_detail,
)
from compras_crawler.web.store import AppStore

CITY = "4202909"
KEY = "id:purchase-1"


def land(warehouse, entity, records, run="first"):
    payload = {"resultado": records, "totalPaginas": 1}
    warehouse.land_page(run_id=run, job_name=entity, entity_name=entity, page_number=1,
                        request_params_json="{}", response_format="json", http_status=200,
                        payload_json=stable_json(payload), payload_text=None, payload_hash=stable_hash(payload))


def buy(key="purchase-1", control="control-1", **extra):
    return dict(idCompra=key, numeroControlePNCP=control, unidadeOrgaoCodigoIbge=int(CITY),
                dataPublicacaoPncp="2026-01-10", objetoCompra="Materiais hospitalares", **extra)


def item(key="item-1", number=1, **extra):
    return dict(idCompra="purchase-1", numeroControlePNCPCompra="control-1", idCompraItem=key,
                numeroItemPncp=number, descricaoResumida="Luva hospitalar", codItemCatalogo=123,
                materialOuServico="M", unidadeMedida="Unidade", quantidade=0, valorUnitarioEstimado=0, **extra)


def result(key="item-1", sequence=1, **extra):
    return dict(idCompra="purchase-1", numeroControlePNCPCompra="control-1", idCompraItem=key,
                sequencialResultado=sequence, numeroItemPncp=1, niFornecedor="12345678000199", tipoPessoa="PJ",
                nomeRazaoSocialFornecedor="Fornecedor de teste", quantidadeHomologada=0,
                valorUnitarioHomologado=0, valorTotalHomologado=0, **extra)


@pytest.fixture
def graph(tmp_path):
    store = AppStore(tmp_path / "workspace")
    store.init_schema()
    store.add_city(CITY, "Brusque", "SC")
    warehouse = BronzeWarehouse(store.city_dir(CITY) / "bronze.duckdb")
    warehouse.init_schema()
    land(warehouse, "pncp_contratacao", [buy()])
    return store, warehouse


def publish(store):
    build_snapshot(store, CITY)
    return purchase_detail(store, CITY, KEY)["snapshot"]


def test_connected_purchase_item_result_supplier_uses_existing_snapshot_only(graph):
    store, warehouse = graph
    land(warehouse, "pncp_item_contratacao", [item()])
    land(warehouse, "pncp_resultado_item", [result()])
    land(warehouse, "fornecedor", [dict(cnpj="12.345.678/0001-99", nomeRazaoSocialFornecedor="Nome no cadastro",
                                       porteEmpresaNome="Microempresa", ativo=False, habilitadoLicitar=True)])
    version = publish(store)
    (store.city_dir(CITY) / "bronze.duckdb").rename(store.city_dir(CITY) / "bronze-not-opened.duckdb")
    detail = purchase_detail(store, CITY, KEY)
    assert detail["coverage"]["status"] == "unverified"
    assert detail["purchase"]["purchase_key"] == KEY
    assert detail["summary"] == dict(item_records=1, result_records=1, confirmed_items=1,
                                     ambiguous_items=0, confirmed_results=1, ambiguous_results=0, results_without_item=0)
    items = purchase_items(store, CITY, KEY, version)
    selected = items["items"][0]
    assert selected["quantity"] == selected["estimated_unit_price"] == 0
    assert selected["purchase_link"]["status"] == "confirmed"
    assert selected["confirmed_results"] == 1
    records = purchase_results(store, CITY, KEY, version, selected["id"])
    award = records["items"][0]
    assert award["item_link"]["status"] == "confirmed"
    assert award["unit_price"] == award["total"] == 0
    assert award["supplier"]["can_open"]
    supplier = supplier_detail(store, CITY, KEY, version, award["id"])
    assert supplier["supplier"]["name"] == "Fornecedor de teste"  # historical name, not overwritten by reference
    assert supplier["registration_status"] == "confirmed"
    assert supplier["registrations"]["items"][0]["name"] == "Nome no cadastro"
    assert supplier["registrations"]["items"][0]["active"] is False
    assert supplier["registrations"]["items"][0]["eligible"] is True
    assert json.loads(award["origin_json"])["entity"] == "pncp_resultado_item"
    with connection(store, CITY) as con:
        assert {r[0] for r in con.execute("SHOW TABLES").fetchall()} == {
            "records", "purchases", "purchase_candidates", "snapshot_metadata"}


def test_conflicting_parents_are_visible_but_never_navigated_as_confirmed(graph):
    store, warehouse = graph
    conflicting = item()
    conflicting["numeroControlePNCPCompra"] = "other-control"
    land(warehouse, "pncp_item_contratacao", [conflicting])
    land(warehouse, "pncp_resultado_item", [result()])
    version = publish(store)
    child = purchase_items(store, CITY, KEY, version)["items"][0]
    assert child["purchase_link"]["status"] == "ambiguous"
    with pytest.raises(ValueError, match="não está confirmado"):
        purchase_results(store, CITY, KEY, version, child["id"])
    award = purchase_results(store, CITY, KEY, version)["items"][0]
    assert award["item_link"]["status"] == "ambiguous"
    assert award["item_record_id"] is None
    assert purchase_detail(store, CITY, KEY)["summary"]["ambiguous_results"] == 1


def test_unique_item_can_prove_purchase_but_not_override_foreign_parent(graph):
    store, warehouse = graph
    land(warehouse, "pncp_item_contratacao", [item()])
    inferred = result(sequence=1)
    inferred.pop("idCompra")
    inferred.pop("numeroControlePNCPCompra")
    foreign = dict(inferred, sequencialResultado=2, idCompra="other-purchase")
    land(warehouse, "pncp_resultado_item", [inferred, foreign])
    version = publish(store)
    awards = {r["sequence"]: r for r in purchase_results(store, CITY, KEY, version)["items"]}
    assert awards["1"]["purchase_link"]["evidence"] == ["idCompraItem"]
    assert awards["1"]["item_link"]["status"] == "confirmed"
    assert awards["2"]["purchase_link"]["status"] == "ambiguous"
    assert not awards["2"]["supplier"]["can_open"]
    with pytest.raises(ValueError, match="não está confirmado"):
        supplier_detail(store, CITY, KEY, version, awards["2"]["id"])


def test_composite_item_reference_requires_unique_number_and_preserves_orphans(graph):
    store, warehouse = graph
    land(warehouse, "pncp_item_contratacao", [item(), item("duplicate", number=1), item("unique", number=2)])
    ambiguous = result()
    ambiguous.pop("idCompraItem")
    unique = dict(ambiguous, sequencialResultado=2, numeroItemPncp=2)
    missing = dict(ambiguous, sequencialResultado=3, numeroItemPncp=3)
    land(warehouse, "pncp_resultado_item", [ambiguous, unique, missing])
    version = publish(store)
    awards = {r["sequence"]: r for r in purchase_results(store, CITY, KEY, version)["items"]}
    assert awards["1"]["item_link"]["status"] == "ambiguous"
    assert awards["2"]["item_link"]["status"] == "confirmed"
    assert awards["2"]["identity_status"] == "unverified"
    assert "numeroItemPncp" in awards["2"]["item_link"]["evidence"]
    assert awards["3"]["item_link"]["status"] == "missing"
    assert purchase_detail(store, CITY, KEY)["summary"]["results_without_item"] == 2


def test_names_catalogs_and_foreign_city_are_not_relationship_keys(graph):
    store, warehouse = graph
    foreign = buy("elsewhere", "else-control")
    foreign["unidadeOrgaoCodigoIbge"] = 9999999
    land(warehouse, "pncp_contratacao", [foreign], run="foreign")
    unrelated = item()
    unrelated.update(idCompra="elsewhere", numeroControlePNCPCompra="else-control")
    land(warehouse, "pncp_item_contratacao", [unrelated])
    land(warehouse, "pncp_resultado_item", [dict(idCompra="elsewhere", descricaoResumida="Luva hospitalar", codItemCatalogo=123)])
    version = publish(store)
    assert purchase_items(store, CITY, KEY, version)["total"] == 0
    assert purchase_results(store, CITY, KEY, version)["total"] == 0
    with pytest.raises(KeyError, match="não encontrada"):
        purchase_detail(store, CITY, "id:elsewhere")
    with pytest.raises(KeyError):
        purchase_detail(store, CITY, "' OR 1=1 --")


def test_explicit_foreign_municipality_is_not_overridden_by_matching_identifiers(graph):
    store, warehouse = graph
    land(warehouse, "pncp_item_contratacao", [item(unidadeOrgaoCodigoIbge=4205407)])
    land(warehouse, "pncp_resultado_item", [result(unidadeOrgaoCodigoIbge=4205407)])
    version = publish(store)
    child = purchase_items(store, CITY, KEY, version)["items"][0]
    award = purchase_results(store, CITY, KEY, version)["items"][0]
    assert child["purchase_link"]["status"] == "ambiguous"
    assert "município explícito divergente" in child["purchase_link"]["reason"]
    assert award["purchase_link"]["status"] == "ambiguous"
    assert not award["supplier"]["can_open"]


def test_supplier_missing_cpf_masking_and_document_type_safety(graph):
    store, warehouse = graph
    award = result()
    award.update(niFornecedor="012.345.678-90", tipoPessoa="PF", nomeRazaoSocialFornecedor="Pessoa de teste")
    land(warehouse, "pncp_resultado_item", [award])
    land(warehouse, "fornecedor", [dict(cnpj="12345678000199", nomeRazaoSocialFornecedor="Pessoa de teste")])
    version = publish(store)
    selected = purchase_results(store, CITY, KEY, version)["items"][0]
    assert selected["unit_price"] == 0
    assert selected["supplier"]["identifier"] == "***.***.***-90"
    assert selected["supplier"]["kind"] == "cpf"
    detail = supplier_detail(store, CITY, KEY, version, selected["id"])
    assert detail["registration_status"] == "missing"
    assert detail["registrations"]["total"] == 0
    assert document("01234567890", "PJ") is None
    assert document("foreign-12345678000199") is None
    assert document("12345678000199", "PE") is None
    assert document("123456789") is None  # do not pad a truncated identifier


def test_multiple_supplier_references_stay_ambiguous_and_cancelled_results_are_labelled(graph):
    store, warehouse = graph
    land(warehouse, "pncp_resultado_item", [result(situacaoCompraItemResultadoNome="Cancelado")])
    land(warehouse, "fornecedor", [dict(cnpj="12345678000199", nomeRazaoSocialFornecedor="Nome A"),
                                   dict(cnpj="12.345.678/0001-99", cpf="invalid", nomeRazaoSocialFornecedor="Nome B")])
    version = publish(store)
    award = purchase_results(store, CITY, KEY, version)["items"][0]
    assert award["cancelled"]
    supplier = supplier_detail(store, CITY, KEY, version, award["id"], size=1)
    assert supplier["registration_status"] == "ambiguous"
    assert supplier["registrations"]["total"] == 2
    assert len(supplier["registrations"]["items"]) == 1
    all_references = supplier_detail(store, CITY, KEY, version, award["id"])
    assert any(row["identity_conflict"] for row in all_references["registrations"]["items"])


def test_pagination_snapshot_pinning_and_latest_record_identity(graph):
    store, warehouse = graph
    land(warehouse, "pncp_item_contratacao", [item(f"item-{i}", i) for i in range(27)])
    land(warehouse, "pncp_resultado_item", [dict(result(f"item-{i}"), numeroItemPncp=i) for i in range(27)])
    land(warehouse, "pncp_resultado_item", [dict(result("item-0"), numeroItemPncp=0)], run="second")
    version = publish(store)
    first = purchase_items(store, CITY, KEY, version)
    second = purchase_items(store, CITY, KEY, version, current=2)
    assert first["total"] == second["total"] == 27
    assert len(first["items"]) == 20 and len(second["items"]) == 7
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    assert purchase_results(store, CITY, KEY, version)["total"] == 27
    build_snapshot(store, CITY)
    with pytest.raises(SnapshotChanged, match="snapshot mudou"):
        purchase_items(store, CITY, KEY, version, current=2)


def test_exploration_http_validation_and_snapshot_conflict(graph):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from compras_crawler.web.app import create_app
    store, warehouse = graph
    land(warehouse, "pncp_item_contratacao", [item()])
    land(warehouse, "pncp_resultado_item", [result()])
    publish(store)
    app = create_app(store.root, start_workers=False)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        base = f"/api/cities/{CITY}"
        detail = client.get(base + "/purchase-detail", params={"purchase_key": KEY})
        assert detail.status_code == 200
        version = detail.json()["snapshot"]
        params = dict(purchase_key=KEY, snapshot=version)
        assert client.get(base + "/purchase-items", params=params).json()["total"] == 1
        awards = client.get(base + "/purchase-results", params=params).json()
        assert client.get(base + "/supplier-detail", params=dict(params, result_id=awards["items"][0]["id"])).status_code == 200
        assert client.get(base + "/purchase-items", params=dict(params, page=0)).status_code == 422
        assert client.get(base + "/purchase-items", params=dict(params, page_size=101)).status_code == 422
        assert client.get(base + "/purchase-results", params=dict(params, item_record_id="../other")).status_code == 422
        assert client.get(base + "/purchase-items", params=dict(params, snapshot="previous")).status_code == 409
        assert client.get(base + "/supplier-detail", params=dict(params, result_id="f" * 64)).status_code == 404
        assert client.get(base + "/purchase-detail", params=dict(purchase_key="unknown")).status_code == 404
        assert client.get(base + "/purchase-detail", params=dict(purchase_key=KEY), headers={"Host": "other:8000"}).status_code == 400
