import pytest

from compras_crawler.client import PageData
from compras_crawler.crawl_state import CrawlStopped
from compras_crawler.full_city import FullCityConfig, FullCityCrawler


class Pages:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def fetch_page(self, path, params, **kwargs):
        page = params.get("pagina", 1)
        self.calls.append(page)
        if page == self.fail:
            raise ConnectionError("offline")
        rows = [{"idCompra": f"p{page}"}]
        return PageData("https://example.test", page, params, rows,
                        {"resultado": rows, "totalPaginas": 2, "paginasRestantes": 2 - page}, "json", 200)


def crawler(tmp_path, **kwargs):
    config = FullCityConfig(db_path=tmp_path / "city", delay_seconds=0, **kwargs)
    obj = FullCityCrawler(config)
    obj.warehouse.init_schema()
    obj.crawl_state.init_schema()
    obj.ops_store.init_schema()
    obj.run_id = "attempt"
    return obj


def fetch(obj):
    return obj.fetch_paginated(job_name="purchases", entity_name="pncp_contratacao", path="/x", params={})


def test_resume_partial_job_does_not_skip_remaining_pages(tmp_path):
    first = crawler(tmp_path)
    first.client = Pages(fail=2)
    assert len(fetch(first)) == 1
    second = crawler(tmp_path)
    second.client = Pages()
    assert len(fetch(second)) == 2
    assert second.client.calls == [2]
    assert len(fetch(second)) == 2
    assert second.client.calls == [2]
    with second.warehouse.connect() as con:
        assert con.execute("SELECT count(*) FROM bronze_pages").fetchone()[0] == 2


def test_checkpoint_failure_does_not_duplicate_bronze_page(tmp_path, monkeypatch):
    first = crawler(tmp_path)
    first.client = Pages()
    monkeypatch.setattr(first.ops_store, "save_checkpoint", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("crash")))
    with pytest.raises(RuntimeError, match="crash"):
        fetch(first)
    second = crawler(tmp_path)
    second.client = Pages()
    assert len(fetch(second)) == 2
    assert second.client.calls == [2]
    with second.warehouse.connect() as con:
        assert con.execute("SELECT count(*) FROM bronze_pages").fetchone()[0] == 2


def test_dates_and_collection_ids_isolate_resume(tmp_path):
    first = crawler(tmp_path, collection_id="one")
    first.client = Pages()
    fetch(first)
    for options in ({"collection_id": "two"}, {"collection_id": "one", "start_date": "2026-02-01"}):
        other = crawler(tmp_path, **options)
        other.client = Pages()
        assert len(fetch(other)) == 2
        assert other.client.calls == [1, 2]


def test_no_resume_keeps_history_without_mixing_generations(tmp_path):
    first = crawler(tmp_path)
    first.client = Pages()
    fetch(first)
    fresh = crawler(tmp_path, resume=False)
    fresh.client = Pages()
    assert len(fetch(fresh)) == 2
    resumed = crawler(tmp_path)
    resumed.client = Pages()
    assert len(fetch(resumed)) == 2
    assert resumed.client.calls == []
    with resumed.warehouse.connect() as con:
        assert con.execute("SELECT count(*) FROM bronze_pages").fetchone()[0] == 4


def test_repeated_pages_and_limits_are_terminal_errors(tmp_path):
    obj = crawler(tmp_path, max_pages_per_job=1)
    obj.client = Pages()
    fetch(obj)
    assert "max_pages" in obj.errors[0]["message"]
    assert not obj.crawl_state.open_job("unknown", "other", resume=True)["complete"]


def test_stop_is_not_swallowed_as_endpoint_failure(tmp_path):
    class Stop:
        def check(self):
            raise CrawlStopped()
    obj = crawler(tmp_path)
    obj.control = Stop()
    with pytest.raises(CrawlStopped):
        fetch(obj)
    assert obj.errors == []


def test_terminal_endpoint_error_marks_run_partial(tmp_path, monkeypatch):
    obj = crawler(tmp_path)
    monkeypatch.setattr(obj, "_run_phases", lambda: obj._record_error("endpoint", 1, "HTTP 400", None))
    result = obj.run()
    assert len(result.errors) == 1
    with obj.ops_store.connect() as con:
        assert con.execute("SELECT status FROM ops_runs WHERE run_id=?", [result.run_id]).fetchone()[0] == "partial"


def test_year_scoped_endpoints_cover_every_year_in_window(tmp_path, monkeypatch):
    obj = crawler(tmp_path, start_date="2025-12-01", end_date="2026-02-01")
    calls = []
    monkeypatch.setattr(obj, "fetch_paginated", lambda **kw: calls.append(kw) or [])
    obj._crawl_legado(["1"])
    years = {call["params"]["dt_ano_aviso"] for call in calls if "dt_ano_aviso" in call["params"]}
    assert years == {2025, 2026}
    calls.clear()
    obj._crawl_pgc(["1"])
    assert {call["params"]["anoPcaProjetoCompra"] for call in calls if "anoPcaProjetoCompra" in call["params"]} == {2025, 2026}


def test_invalid_date_window_rejected():
    with pytest.raises(ValueError):
        FullCityConfig(start_date="2026-02-01", end_date="2026-01-01")
