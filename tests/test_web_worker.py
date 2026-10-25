import os
from types import SimpleNamespace

import pytest

import compras_crawler.web.worker as worker
from compras_crawler.crawl_state import CrawlStopped
from compras_crawler.normalize import stable_hash, stable_json
from compras_crawler.storage import BronzeWarehouse
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
