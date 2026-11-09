"""Offline tests for the PNCP direct client and collector (plan acceptance items 4-6)."""
from __future__ import annotations

import json

import pytest
import requests

import compras_crawler.pncp_direct as module
from compras_crawler.client import PageData
from compras_crawler.crawl_state import CrawlStopped
from compras_crawler.normalize import stable_json
from compras_crawler.pncp_direct import (
    PncpDirectClient,
    PncpDirectCollector,
    PncpDirectConfig,
    control_incoherence,
    parse_pncp_control,
    quantity_from_payload,
    supplier_identity,
)

CONTROL = "34123456000100-1-000123/2026"
CNPJ = "34123456000100"
CONSULTA = "https://pncp.gov.br/api/consulta/v1"
PNCP = "https://pncp.gov.br/api/pncp/v1"
LISTING_URL = f"{CONSULTA}/contratacoes/publicacao"
ITEMS_URL = f"{PNCP}/orgaos/{CNPJ}/compras/2026/123/itens"
QUANTITY_URL = f"{ITEMS_URL}/quantidade"
ITEMS_JOB = "pncp_direto_itens_34123456000100-1-000123_2026"
QUANTITY_JOB = "pncp_direto_quantidade_itens_34123456000100-1-000123_2026"
RESULTS_JOB = "pncp_direto_resultados_item_1_34123456000100-1-000123_2026"


# ------------------------------------------------------------- sample fixtures


def purchase_row(**overrides):
    row = {
        "numeroControlePNCP": CONTROL,
        "anoCompra": 2026,
        "sequencialCompra": 123,
        "orgaoEntidade": {"cnpj": CNPJ, "razaoSocial": "PREFEITURA"},
        "unidadeOrgao": {"codigoIbge": 4202909, "codigoUnidade": "G"},
        "objetoCompra": "objeto de teste",
    }
    row.update(overrides)
    return row


def item_row(numero_item, **overrides):
    row = {"numeroItem": numero_item, "descricao": f"item {numero_item}", "temResultado": True}
    row.update(overrides)
    return row


def result_row(numero_item, sequencial=1, **overrides):
    row = {
        "numeroControlePNCPCompra": CONTROL,
        "numeroItem": numero_item,
        "sequencialResultado": sequencial,
        "fornecedor": {"tipoPessoa": "PJ", "niFornecedor": "98765432000100"},
    }
    row.update(overrides)
    return row


def listing_payload(records, page=1, total_pages=1):
    return {
        "data": records,
        "totalRegistros": len(records),
        "totalPaginas": total_pages,
        "numeroPagina": page,
        "paginasRestantes": total_pages - page,
    }


# --------------------------------------------------------- collector plumbing


class FakePncp:
    """Route-driven offline replacement for PncpDirectClient.fetch."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def fetch(self, url, params, *, expect):
        self.calls.append({"expect": expect, "url": url, "params": dict(params)})
        return self.handler(expect, url, dict(params))


def page(expect, url, params, raw):
    number = int(params.get("pagina", 1) or 1)
    if isinstance(raw, list):
        records = [row for row in raw if isinstance(row, dict)]
    elif expect == "listing" and isinstance(raw, dict) and isinstance(raw.get("data"), list):
        records = [row for row in raw["data"] if isinstance(row, dict)]
    else:
        records = []
    return PageData(url, number, dict(params), records, raw, "application/json", 200)


def default_handler(expect, url, params):
    """One valid modality purchase with one item with one result."""
    if url == LISTING_URL:
        return page(expect, url, params, listing_payload([purchase_row()]))
    if url == ITEMS_URL:
        return page(expect, url, params, [item_row(1)])
    if url == QUANTITY_URL:
        return page(expect, url, params, 1)
    if url.endswith("/resultados"):
        numero = int(url.rsplit("/", 2)[-2])
        return page(expect, url, params, [result_row(numero)])
    raise AssertionError(url)


def collector(tmp_path, handler=None, init_schema=True, **overrides):
    defaults = dict(db_path=tmp_path / "city", delay_seconds=0, modalities=(6,))
    defaults.update(overrides)
    obj = PncpDirectCollector(PncpDirectConfig(**defaults))
    if init_schema:
        obj.warehouse.init_schema()
        obj.crawl_state.init_schema()
        obj.ops_store.init_schema()
        obj.run_id = "attempt"
    if handler is not None:
        obj.client = FakePncp(handler)
    return obj


def distinct_entities(obj):
    with obj.warehouse.connect() as con:
        rows = con.execute("SELECT DISTINCT entity_name FROM bronze_pages").fetchall()
    return {row[0] for row in rows}


def page_numbers(obj, job_name):
    with obj.warehouse.connect() as con:
        rows = con.execute(
            "SELECT page_number FROM bronze_pages WHERE job_name = ? ORDER BY page_number",
            [job_name],
        ).fetchall()
    return [row[0] for row in rows]


# ---------------------------------------------------------------- client level


def test_client_never_sends_credentials_to_pncp(monkeypatch):
    monkeypatch.setenv("COMPRAS_GOV_TOKEN", "secret-token-value")
    headers_seen = []

    class Session:
        def get(self, url, params=None, headers=None, timeout=None, allow_redirects=None):
            headers_seen.append(headers)
            raise RuntimeError("done")

    client = PncpDirectClient(session=Session())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        client.fetch(f"{PNCP}/modalidades", {}, expect="children")
    assert headers_seen == [{"Accept": "application/json"}]


def test_client_treats_204_as_valid_empty_response():
    session = FakeSession([FakeResponse(status_code=204)])
    client = PncpDirectClient(session=session)  # type: ignore[arg-type]
    result = client.fetch(ITEMS_URL, {"pagina": 1}, expect="children")
    assert result.status_code == 204
    assert result.raw is None
    assert result.records == []
    assert session.calls[0]["headers"] == {"Accept": "application/json"}


def test_client_rejects_invalid_json():
    session = FakeSession([FakeResponse(status_code=200, invalid_json=True)])
    client = PncpDirectClient(session=session)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="invalid JSON"):
        client.fetch(ITEMS_URL, {"pagina": 1}, expect="children")


def test_client_rejects_redirects_and_out_of_scope_urls():
    redirect = FakeResponse(status_code=302, extra_headers={"Location": "https://example.com/x"})
    client = PncpDirectClient(session=FakeSession([redirect]))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="redirect"):
        client.fetch(f"{PNCP}/modalidades", {}, expect="children")
    with pytest.raises(ValueError, match="restricted"):
        PncpDirectClient().fetch("https://example.invalid/api/consulta/v1/x", {}, expect="children")
    with pytest.raises(ValueError, match="outside the documented public API roots"):
        PncpDirectClient().fetch("https://pncp.gov.br/api/pncp/v3/admin", {}, expect="children")
    with pytest.raises(ValueError, match="https://"):
        PncpDirectClient().fetch("http://pncp.gov.br/api/consulta/v1/x", {}, expect="children")
    with pytest.raises(ValueError, match="query string"):
        PncpDirectClient().fetch(f"{PNCP}/modalidades?x=1", {}, expect="children")


def test_client_retries_rate_limit_with_shared_throttle_pause():
    sleeps: list[float] = []
    session = FakeSession([
        FakeResponse(status_code=429, extra_headers={"Retry-After": "7"}),
        FakeResponse(json_data=[item_row(1)]),
    ])
    client = PncpDirectClient(session=session, max_retries=1, sleep_fn=sleeps.append)  # type: ignore[arg-type]
    result = client.fetch(ITEMS_URL, {"pagina": 1}, expect="children")
    assert result.status_code == 200
    assert sleeps == [7.0]
    assert len(session.calls) == 2


def test_client_retries_connection_errors():
    session = FlakySession([requests.ConnectionError("down"), FakeResponse(json_data=[item_row(1)])])
    client = PncpDirectClient(session=session, sleep_fn=lambda seconds: None)  # type: ignore[arg-type]
    result = client.fetch(ITEMS_URL, {"pagina": 1}, expect="children")
    assert result.records == [item_row(1)]
    assert len(session.calls) == 2


def test_client_contracts_per_operation():
    session = FakeSession([
        FakeResponse(json_data=listing_payload([purchase_row()])),
        FakeResponse(json_data=[item_row(1)]),
        FakeResponse(json_data={"mensagem": "objeto de erro"}),
        FakeResponse(json_data={"numeroControlePNCP": CONTROL, "anoCompra": 2026}),
        FakeResponse(json_data={"status": "sem data"}),
    ])
    client = PncpDirectClient(session=session)  # type: ignore[arg-type]

    listing = client.fetch(LISTING_URL, {"pagina": 1}, expect="listing")
    assert listing.records[0]["numeroControlePNCP"] == CONTROL

    items = client.fetch(ITEMS_URL, {}, expect="children")
    assert items.records == [item_row(1)]

    with pytest.raises(ValueError, match="not a purchase"):
        client.fetch(f"{CONSULTA}/orgaos/{CNPJ}/compras/2026/123", {}, expect="detail")
    detail = client.fetch(f"{CONSULTA}/orgaos/{CNPJ}/compras/2026/123", {}, expect="detail")
    assert detail.records[0]["numeroControlePNCP"] == CONTROL

    with pytest.raises(ValueError, match="without a data array"):
        client.fetch(LISTING_URL, {}, expect="listing")


# -------------------------------------------------------------- collector level


def test_full_offline_run_is_navigable_without_legacy_ids(tmp_path):
    obj = collector(tmp_path, default_handler)
    result = obj.run()
    assert result.stats["pncp_direto_listagem_mod_6"]["pages"] == 1
    assert result.stats[ITEMS_JOB]["quantity_observed"] == 1
    assert distinct_entities(obj) == {
        "pncp_direct_contratacao",
        "pncp_direct_item_contratacao",
        "pncp_direct_resultado_item",
    }
    with obj.warehouse.connect() as con:
        jobs = {row[0] for row in con.execute(
            "SELECT DISTINCT job_name FROM bronze_pages").fetchall()}
    assert QUANTITY_JOB in jobs and RESULTS_JOB in jobs


def test_provenance_keeps_route_parentage_and_contract(tmp_path):
    obj = collector(tmp_path, default_handler)
    obj.run()
    with obj.warehouse.connect() as con:
        metas = con.execute(
            "SELECT request_params_json FROM bronze_pages WHERE entity_name = 'pncp_direct_item_contratacao'"
        ).fetchall()
    meta = json.loads(metas[0][0])
    assert meta["_pncp_source"] == "pncp_direct"
    assert meta["_pncp_contract"] == module.PNCP_CONTRACT_VERSION
    assert meta["_pncp_endpoint_kind"] == "itens"
    assert meta["_pncp_route"] == f"/api/pncp/v1/orgaos/{CNPJ}/compras/2026/123/itens"
    assert meta["_pncp_parent_control"] == CONTROL


def test_listing_two_pages_are_walked_and_validated(tmp_path):
    calls: list[int] = []

    def handler(expect, url, params):
        if url == LISTING_URL:
            number = int(params.get("pagina", 1))
            calls.append(number)
            records = [purchase_row()] if number == 1 else []
            return page(expect, url, params, listing_payload(records, page=number, total_pages=2))
        return default_handler(expect, url, params)

    result = collector(tmp_path, handler).run()
    assert calls == [1, 2]
    assert result.stats["listagem"]["purchases_valid"] == 1


def test_municipal_mismatch_and_control_incoherence_are_excluded(tmp_path):
    def handler(expect, url, params):
        if url == LISTING_URL:
            rows = [
                purchase_row(),
                purchase_row(unidadeOrgao={"codigoIbge": 4209999, "codigoUnidade": "X"}),
                purchase_row(anoCompra=2025),
            ]
            return page(expect, url, params, listing_payload(rows))
        return default_handler(expect, url, params)

    obj = collector(tmp_path, handler)
    result = obj.run()
    assert result.stats["listagem"]["purchases_excluded"] == 2
    assert result.stats["listagem"]["purchases_valid"] == 1
    messages = [error["message"] for error in result.errors]
    assert any("município retornado diverge" in message for message in messages)
    assert any("anoCompra" in message for message in messages)
    # Only the valid purchase fans out.
    assert result.stats[ITEMS_JOB]["records"] == 1


def test_repeated_listing_page_before_completion_is_terminal(tmp_path):
    calls: list[int] = []

    def handler(expect, url, params):
        if url == LISTING_URL:
            number = int(params.get("pagina", 1)) or 1
            calls.append(number)
            return page(expect, url, params, listing_payload([purchase_row()], page=number, total_pages=3))
        return default_handler(expect, url, params)

    obj = collector(tmp_path, handler)
    obj.run()
    assert calls == [1, 2]  # the identical third page is never requested
    assert any("repeated page" in error["message"] for error in obj.errors)


def test_tem_resultado_false_means_not_published_not_absent(tmp_path):
    def handler(expect, url, params):
        if url == ITEMS_URL:
            return page(expect, url, params, [item_row(1, temResultado=False), item_row(2)])
        return default_handler(expect, url, params)

    obj = collector(tmp_path, handler)
    obj.run()
    assert obj.stats[ITEMS_JOB]["results_not_published"] == 1
    requested = [call["url"] for call in obj.client.calls if call["url"].endswith("/resultados")]
    assert f"{ITEMS_URL}/1/resultados" not in requested
    assert f"{ITEMS_URL}/2/resultados" in requested


def test_item_without_stable_id_is_explicit_and_has_no_fanout(tmp_path):
    def handler(expect, url, params):
        if url == ITEMS_URL:
            return page(expect, url, params, [item_row(None), item_row(2)])
        return default_handler(expect, url, params)

    obj = collector(tmp_path, handler)
    obj.run()
    assert any("item sem identificador estável" in error["message"] for error in obj.errors)
    requested = [call["url"] for call in obj.client.calls if call["url"].endswith("/resultados")]
    assert f"{ITEMS_URL}/2/resultados" in requested


def test_result_contradicting_parentage_is_not_silently_linked(tmp_path):
    def handler(expect, url, params):
        if url.endswith("/resultados"):
            return page(expect, url, params, [
                result_row(1),
                result_row(1, numeroControlePNCPCompra="99999999000000-1-000999/2026"),
                result_row(5),
            ])
        return default_handler(expect, url, params)

    obj = collector(tmp_path, handler)
    obj.run()
    messages = [error["message"] for error in obj.errors]
    assert any("contradiz a parentagem do endpoint" in message for message in messages)
    assert any("contraditório" in message for message in messages)


def test_quantity_divergence_is_recorded_not_silently_completed(tmp_path):
    def handler(expect, url, params):
        if url == QUANTITY_URL:
            return page(expect, url, params, 3)
        return default_handler(expect, url, params)

    obj = collector(tmp_path, handler)
    result = obj.run()
    assert any("divergência de quantidade: fonte=3 coletado=1" in error["message"] for error in result.errors)
    assert result.stats[ITEMS_JOB]["quantity_observed"] == 3


def test_sigilo_and_cancelled_values_stay_untouched_in_bronze(tmp_path):
    sigiloso_item = item_row(1, orcamentoSigiloso=True, valorHomologado=None)
    cancelled_result = result_row(1, dataCancelamento="2026-01-15T00:00:00")

    def handler(expect, url, params):
        if url == ITEMS_URL:
            return page(expect, url, params, [sigiloso_item])
        if url.endswith("/resultados"):
            return page(expect, url, params, [cancelled_result])
        return default_handler(expect, url, params)

    obj = collector(tmp_path, handler)
    obj.run()
    with obj.warehouse.connect() as con:
        bronze_item = con.execute(
            "SELECT payload_json FROM bronze_pages WHERE entity_name = 'pncp_direct_item_contratacao'"
        ).fetchone()[0]
        bronze_result = con.execute(
            "SELECT payload_json FROM bronze_pages WHERE entity_name = 'pncp_direct_resultado_item'"
        ).fetchone()[0]
    assert bronze_item == stable_json([sigiloso_item])
    assert '"valorHomologado":null' in bronze_item
    assert bronze_result == stable_json([cancelled_result])


def test_resume_of_interrupted_listing_fans_out_only_the_missing_part(tmp_path):
    offline = {"fail": True}

    def handler(expect, url, params):
        if url == LISTING_URL and offline["fail"] and int(params.get("pagina", 1)) == 2:
            raise requests.ConnectionError("connection failure")
        if url == LISTING_URL:
            number = int(params.get("pagina", 1))
            records = [purchase_row()] if number == 1 else []
            return page(expect, url, params, listing_payload(records, page=number, total_pages=2))
        return default_handler(expect, url, params)

    first = collector(tmp_path, handler)
    result = first.run()
    assert any("connection failure" in error["message"] for error in result.errors)
    assert page_numbers(first, "pncp_direto_listagem_mod_6") == [1]

    offline["fail"] = False
    second = collector(tmp_path, handler)
    second.run()
    listing_calls = [call for call in second.client.calls if call["url"] == LISTING_URL]
    # Page 1 is replayed from Bronze; only the missing page is fetched.
    assert [call["params"]["pagina"] for call in listing_calls] == [2]
    with second.warehouse.connect() as con:
        total = con.execute("SELECT count(*) FROM bronze_pages").fetchone()[0]
    # listing two pages + items + quantity + results, exactly once each
    assert total == 5
    assert page_numbers(second, "pncp_direto_listagem_mod_6") == [1, 2]


def test_checkpoint_failure_does_not_duplicate_bronze_page(tmp_path, monkeypatch):
    obj = collector(tmp_path, default_handler)
    real_save = obj.ops_store.save_checkpoint

    def crashing_save(job_name, **kwargs):
        real_save(job_name, **kwargs)
        raise RuntimeError("crash after commit")

    monkeypatch.setattr(obj.ops_store, "save_checkpoint", crashing_save)
    with pytest.raises(RuntimeError, match="crash after commit"):
        obj.run()
    with obj.warehouse.connect() as con:
        assert con.execute("SELECT count(*) FROM bronze_pages").fetchone()[0] == 1

    # The page and the checkpoint advance committed atomically in the same
    # DuckDB transaction, so a lost Ops acknowledgement is replayed without
    # re-fetching or duplicating anything.
    replay = collector(tmp_path, default_handler)
    replay.run()
    listing_calls = [call for call in replay.client.calls if call["url"] == LISTING_URL]
    assert listing_calls == []
    with replay.warehouse.connect() as con:
        total = con.execute("SELECT count(*) FROM bronze_pages").fetchone()[0]
        listing_rows = con.execute(
            "SELECT count(*) FROM bronze_pages WHERE job_name = 'pncp_direto_listagem_mod_6'"
        ).fetchone()[0]
    assert listing_rows == 1  # exactly one observation, no duplicate
    assert total == 4  # the fanout phases that never ran are now collected
    assert page_numbers(replay, "pncp_direto_listagem_mod_6") == [1]


def test_collections_and_dates_produce_distinct_resume_keys(tmp_path):
    collector(tmp_path, default_handler, collection_id="one").run()
    collector(tmp_path, default_handler, collection_id="two").run()
    obj = collector(tmp_path, init_schema=False)
    with obj.warehouse.connect() as con:
        jobs = con.execute(
            "SELECT count(*) FROM bronze_crawl_jobs WHERE job_name = 'pncp_direto_listagem_mod_6'"
        ).fetchone()[0]
    assert jobs == 2  # keys vary per collection: no checkpoint reuse under one name


def test_stop_control_interrupts_without_endpoint_errors(tmp_path):
    class Stop:
        def check(self):
            raise CrawlStopped()

    obj = collector(tmp_path, default_handler)
    obj.control = Stop()
    with pytest.raises(CrawlStopped):
        obj.run()
    assert obj.errors == []
    with obj.ops_store.connect() as con:
        status = con.execute("SELECT status FROM ops_runs").fetchone()[0]
    assert status == "stopped"


def test_empty_valid_listing_is_not_an_error_and_run_finishes(tmp_path):
    def handler(expect, url, params):
        if url == LISTING_URL:
            return page(expect, url, params, listing_payload([]))
        raise AssertionError("no fanout without purchases")

    obj = collector(tmp_path, handler)
    result = obj.run()
    assert result.errors == ()
    assert result.stats["pncp_direto_listagem_mod_6"]["records"] == 0


def test_failed_item_source_keeps_listing_and_stays_partial(tmp_path):
    def handler(expect, url, params):
        if url == ITEMS_URL:
            raise requests.ConnectionError("connection failure")
        return default_handler(expect, url, params)

    obj = collector(tmp_path, handler)
    result = obj.run()
    messages = [error["message"] for error in result.errors]
    assert any("connection failure" in message for message in messages)
    # Listing data is preserved; the run is explicitly partial, not a full success.
    assert page_numbers(obj, "pncp_direto_listagem_mod_6") == [1]
    with obj.ops_store.connect() as con:
        status = con.execute("SELECT status FROM ops_runs WHERE run_id = ?", [result.run_id]).fetchone()[0]
    assert status == "partial"


def test_modality_domain_shapes_new_listings(tmp_path):
    def handler(expect, url, params):
        if url == f"{PNCP}/modalidades":
            return page(expect, url, params, [{"codigo": 6}, {"codigo": "7"}, {"nome": "sem codigo"}])
        return default_handler(expect, url, params)

    obj = collector(tmp_path, handler, modalities=None)
    obj.run()
    modalities = {
        call["params"]["codigoModalidadeContratacao"]
        for call in obj.client.calls
        if call["url"] == LISTING_URL
    }
    assert modalities == {6, 7}


def test_no_token_string_leaks_into_bronze_or_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPRAS_GOV_TOKEN", "secret-token-value")
    obj = collector(tmp_path, default_handler)
    result = obj.run()
    with obj.warehouse.connect() as con:
        for params_json, payload_json in con.execute(
            "SELECT request_params_json, payload_json FROM bronze_pages"
        ).fetchall():
            assert "secret-token-value" not in (params_json or "")
            assert "secret-token-value" not in (payload_json or "")
    for error in result.errors:
        assert "secret-token-value" not in str(error)


# ----------------------------------------------------------------- validation


def test_config_validation():
    with pytest.raises(ValueError, match="page_size"):
        PncpDirectConfig(modalities=(6,), page_size=100)
    with pytest.raises(ValueError, match="page_size"):
        PncpDirectConfig(modalities=(6,), page_size=5)
    with pytest.raises(ValueError, match="consulta_api_base"):
        PncpDirectConfig(modalities=(6,), consulta_api_base="https://example.com/api/consulta/v1")
    with pytest.raises(ValueError, match="start_date"):
        PncpDirectConfig(modalities=(6,), start_date="2026-02-01", end_date="2026-01-01")
    with pytest.raises(ValueError, match="state_uf"):
        PncpDirectConfig(modalities=(6,), state_uf="S")
    with pytest.raises(ValueError, match="modalities"):
        PncpDirectConfig(modalities=())


def test_control_and_identifier_parsing():
    assert parse_pncp_control(CONTROL) == {"cnpj": CNPJ, "segmento": 1, "sequencial": 123, "ano": 2026}
    assert parse_pncp_control("formato estranho") is None
    assert control_incoherence(CONTROL, purchase_row()) == []
    assert control_incoherence(CONTROL, purchase_row(anoCompra=2025)) != []
    assert supplier_identity(result_row(1)) == {"tipo": "PJ", "documento": "98765432000100"}
    assert supplier_identity({"tipoPessoa": "PE", "niFornecedor": "ID-ESTRANGEIRO"}) == {
        "tipo": "PE",
        "documento": "ID-ESTRANGEIRO",
    }
    assert supplier_identity({"fornecedor": {"tipoPessoa": "PJ"}}) is None
    assert quantity_from_payload(2) == 2
    assert quantity_from_payload({"quantidadeItens": 4}) == 4
    assert quantity_from_payload(True) is None
    assert quantity_from_payload({"qtd": "n"}) is None


# ------------------------------------------------------------------- plumbing


class FakeResponse:
    def __init__(self, json_data=None, status_code=200, extra_headers=None, invalid_json=False):
        self._json = json_data
        self.status_code = status_code
        self.headers = {"content-type": "application/json", **(extra_headers or {})}
        self._invalid = invalid_json

    def json(self):
        if self._invalid or self._json is None:
            raise ValueError("no json payload")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None, allow_redirects=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        response = self.responses.pop(0)
        response.headers = dict(response.headers)
        return response


class FlakySession(FakeSession):
    def get(self, url, params=None, headers=None, timeout=None, allow_redirects=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        response = item
        response.headers = dict(response.headers)
        return response


HeaderView = dict
