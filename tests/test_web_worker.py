import os
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
import requests

import compras_crawler.web.worker as worker
from compras_crawler.crawl_state import CrawlStopped
from compras_crawler.normalize import stable_hash, stable_json
from compras_crawler.storage import BronzeWarehouse
from compras_crawler.web.analytics import connection
from compras_crawler.web.exploration import purchase_detail, purchase_items, purchase_results, supplier_detail
from compras_crawler.web.runtime import WorkerControl, file_lock
from compras_crawler.web.store import AppStore


@pytest.fixture
def job(tmp_path):
    store = AppStore(tmp_path)
    store.init_schema()
    store.add_city("4202909", "Brusque", "SC")
    store.begin_service("service")
    run_id = store.enqueue("4202909", dict(start_date="2026-01-01", end_date="2026-01-31"))
    assert store.claim("service")["id"] == run_id
    return store, run_id


def test_worker_publishes_snapshot_and_finishes_without_network(job, monkeypatch):
    store, run_id = job

    class FakeCrawler:
        def __init__(self, config, **kwargs):
            self.config = config
        def run(self):
            warehouse = BronzeWarehouse(self.config.bronze_db_path)
            warehouse.init_schema()
            payload = {"resultado": [dict(idCompra="real-fixture", unidadeOrgaoCodigoIbge=4202909,
                                          dataPublicacaoPncp="2026-01-10")]}
            warehouse.land_page(run_id="crawl", job_name="purchases", entity_name="pncp_contratacao", page_number=1,
                                request_params_json="{}", response_format="json", http_status=200,
                                payload_json=stable_json(payload), payload_text=None, payload_hash=stable_hash(payload))
            return SimpleNamespace(run_id="crawl", stats={}, errors=(), skipped_operations=())

    monkeypatch.setattr(worker, "FullCityCrawler", FakeCrawler)
    worker.execute(store, run_id, "service", os.getppid(), 0)
    assert store.run(run_id)["status"] == "finished"
    assert store.city("4202909")["snapshot"]
    assert store.events(run_id)


def test_cooperative_stop_preserves_user_intent(job, monkeypatch):
    store, run_id = job

    class FakeCrawler:
        def __init__(self, *args, **kwargs):
            pass
        def run(self):
            store.request_stop(run_id)
            raise CrawlStopped()

    monkeypatch.setattr(worker, "FullCityCrawler", FakeCrawler)
    worker.execute(store, run_id, "service", os.getppid(), 0)
    assert store.run(run_id)["status"] == "stopped"
    assert store.city("4202909")["snapshot"] is None


def test_previous_city_worker_is_fenced_by_file_lock(job):
    store, run_id = job
    with file_lock(store.city_dir("4202909") / "writer.lock"):
        worker.execute(store, run_id, "service", os.getppid(), 0)
    assert store.run(run_id)["status"] == "queued"


def test_replaced_service_revokes_control(job):
    store, run_id = job
    control = WorkerControl(store, run_id, "service", os.getppid(), 0)
    control.check()
    store.begin_service("replacement")
    with pytest.raises(CrawlStopped):
        control.check()


@pytest.mark.parametrize("terminal", [None, "stop", "disk"])
def test_two_sources_share_lock_throttle_and_keep_source_outcomes(job, monkeypatch, terminal):
    store, run_id = job
    with store.connect() as con:
        con.execute("""UPDATE runs SET config_json=json_set(config_json,'$.collection_sources',
            json('["comprasgov","pncp_direct"]')) WHERE id=?""", [run_id])
    monkeypatch.setenv("COMPRAS_GOV_TOKEN", "compras-only")
    calls = []

    def factory(source):
        class Fake:
            def __init__(self, config, *, reporter, control, throttle):
                self.config = config
                self.control = control
                calls.append((source, throttle))
                assert getattr(config, "token", None) == ("compras-only" if source == "comprasgov" else None)
            def run(self):
                path = store.city_dir("4202909") / "writer.lock"
                with pytest.raises(RuntimeError), file_lock(path):
                    pytest.fail("writer was not locked")
                if source == "pncp_direct":
                    if terminal == "stop":
                        store.request_stop(run_id)
                        self.control.check()
                    if terminal == "disk":
                        raise OSError("reserva mínima de espaço em disco atingida")
                    BronzeWarehouse(self.config.bronze_db_path).init_schema()
                return SimpleNamespace(run_id=source, stats={}, skipped_operations=(),
                                       errors=({"message": "OCDS retornou 400"},) if source == "comprasgov" else ())
        return Fake

    monkeypatch.setattr(worker, "PncpDirectCollector", factory("pncp_direct"), raising=False)
    monkeypatch.setattr(worker, "FullCityCrawler", factory("comprasgov"))
    worker.execute(store, run_id, "service", os.getppid(), 0)
    run = store.run(run_id)
    if terminal:
        assert [source for source, _ in calls] == ["pncp_direct"]
        assert run["status"] == {"stop": "stopped", "disk": "failed"}[terminal]
        assert store.city("4202909")["snapshot"] is None
    else:
        assert [source for source, _ in calls] == ["pncp_direct", "comprasgov"]
        assert calls[0][1] is calls[1][1]
        assert run["status"] == "partial"
        assert run["result"]["coverage"]["sources"]["pncp_direct"]["status"] == "complete"
        assert run["result"]["coverage"]["sources"]["comprasgov"]["status"] == "partial"


@pytest.mark.parametrize(("pages", "records", "error", "expected"), [
    (1, 0, None, "empty"),
    (1, 2, None, "complete"),
    (0, 0, "HTTP 503: indisponível", "unavailable"),
    (0, 0, "HTTP 400: inválida", "error"),
    (1, 0, "repeated page before pagination completed", "error"),
])
def test_stage_eval_distinguishes_empty_from_failure(pages, records, error, expected):
    name = "pncp_direto_listagem_mod_8"
    stats = {name: {"pages": pages, "records": records}}
    errors = [dict(job_name=name, message=error)] if error else []
    stages = worker.stage_coverage("pncp_direct", stats, errors)
    assert stages["listing"] == {"status": expected, "pages": pages, "records": records}
    assert stages["items"]["status"] == "not_collected"


def test_coverage_does_not_mark_fanout_truncated_children_complete():
    stats = {"pncp_direto_listagem_mod_8": {"pages": 1, "records": 5},
             "pncp_direto_itens_example": {"pages": 1, "records": 1}}
    errors = [{"job_name": "fanout_limit", "message": "fanout truncated: 5 compras limited to 1"}]
    stages = worker.stage_coverage("pncp_direct", stats, errors)
    assert stages["listing"]["status"] == "complete"
    assert stages["items"]["status"] == "error"
    assert stages["results"]["status"] == "error"


def test_eval_brusque_end_to_end_and_recollection_both_sources_simulated(job, monkeypatch):
    store, run_id = job
    city = "4202909"
    prefeitura = "83102343000194"
    federal = "10635424000186"
    can_open = f"{prefeitura}-1-000001/2026"
    sources = ["comprasgov", "pncp_direct"]
    config = dict(start_date="2026-01-01", end_date="2026-01-31", collection_sources=sources)
    token = "never-forward-this-marker"
    monkeypatch.setenv("COMPRAS_GOV_TOKEN", token)
    with store.connect() as con:
        con.execute("UPDATE runs SET config_json=? WHERE id=?", [json.dumps(config), run_id])
    calls = []
    gate = []
    monkeypatch.setattr(worker.SharedThrottle, "wait", lambda self: gate.append(id(self)))

    def buy(cnpj, ibge):
        return dict(numeroControlePNCP=f"{cnpj}-1-000001/2026", anoCompra=2026, sequencialCompra=1,
                    orgaoEntidade={"cnpj": cnpj}, unidadeOrgao={"codigoIbge": ibge},
                    dataPublicacaoPncp="2026-01-15", objetoCompra="Teste sintético")

    def get(session, url, *, params, headers, **kwargs):
        target = urlsplit(url)
        calls.append(target.hostname)
        assert len(gate) == len(calls), "each network call must pass the shared gate"
        assert token not in json.dumps([url, params, headers, dict(session.headers)])
        assert kwargs.get("allow_redirects") is False
        status = 200
        if target.hostname == "pncp.gov.br":
            if target.path.endswith("/modalidades"):
                body = [{"id": 8, "nome": "Dispensa", "statusAtivo": True}]
            elif target.path.endswith("/publicacao"):
                assert params["codigoMunicipioIbge"] == int(city) and params["dataInicial"] == "20260101"
                body = dict(data=[buy(prefeitura, int(city)), buy(federal, int(city))],
                            numeroPagina=1, totalRegistros=2, totalPaginas=1, paginasRestantes=0)
            elif target.path.endswith("/itens/quantidade"):
                body = 1 if prefeitura in target.path else 0
            elif target.path.endswith("/itens"):
                body = [{"numeroItem": 1, "descricao": "Material", "temResultado": True}] if prefeitura in target.path else []
            elif target.path.endswith("/resultados"):
                body = [{"numeroItem": 1, "sequencialResultado": 1, "niFornecedor": "98765432101",
                         "tipoPessoa": "PF", "valorTotalHomologado": 0}]
            else:
                pytest.fail(f"Unexpected PNCP route {target.path}")
        else:
            assert target.hostname == "dadosabertos.compras.gov.br"
            body = dict(resultado=[], paginasRestantes=0, totalPaginas=0)
        response = requests.Response()
        response.status_code = status
        response.url = url
        response.headers["Content-Type"] = "application/json"
        response._content = json.dumps(body).encode()
        return response

    monkeypatch.setattr(requests.Session, "get", get)
    for attempt in range(2):
        if attempt:
            run_id = store.enqueue(city, config)
            assert store.claim("service")["id"] == run_id
        first_call = len(calls)
        worker.execute(store, run_id, "service", os.getppid(), 0)
        assert calls[first_call] == "pncp.gov.br"
        assert len(set(gate[first_call:])) == 1
        run = store.run(run_id)
        assert run["status"] == "finished", run["result"]
        coverage = run["result"]["coverage"]["sources"]
        assert coverage["comprasgov"]["stages"]["listing"]["status"] == "empty"
        assert coverage["pncp_direct"]["stages"]["listing"]["status"] == "complete"
        with connection(store, city) as con:
            eligible = con.execute("""SELECT control FROM purchases
                WHERE resolved_city=? AND json_extract_string(payload_json,'$.orgaoEntidade.cnpj')=?
                AND published_on BETWEEN '2026-01-01' AND '2026-01-31'""", [city, prefeitura]).fetchall()
            assert eligible == [(can_open,)]
            assert con.execute("SELECT count(*) FROM purchases").fetchone() == (2,)
            assert not con.execute("SELECT count(*) FROM records WHERE origin_json LIKE ?", [f"%{token}%"]).fetchone()[0]
        key = f"pncp:{can_open}"
        detail = purchase_detail(store, city, key)
        snapshot = detail["snapshot"]
        assert detail["conciliation"]["selected_source"] == "pncp_direct"
        item = purchase_items(store, city, key, snapshot)["items"][0]
        results = purchase_results(store, city, key, snapshot, item_record_id=item["id"])
        award = results["items"][0]
        assert award["total"] == 0 and award["supplier"]["identifier"] == "***.***.***-01"
        assert supplier_detail(store, city, key, snapshot, award["id"])["registration_status"] == "missing"
    with BronzeWarehouse(store.city_dir(city) / "bronze.duckdb").connect() as con:
        assert con.execute("SELECT count(DISTINCT run_id) FROM bronze_pages WHERE entity_name='pncp_direct_contratacao'").fetchone() == (2,)
