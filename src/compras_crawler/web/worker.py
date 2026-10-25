"""Isolated city worker. Invoked by the local service, never by HTTP parameters."""
from __future__ import annotations

from pathlib import Path
import os
import sys

from ..crawl_state import CrawlStopped
from ..full_city import FullCityConfig, FullCityCrawler
from .analytics import build_snapshot
from .runtime import SharedThrottle, WorkerControl, file_lock
from .store import AppStore


class Reporter:
    def __init__(self, store: AppStore, run_id: str, token: str | None):
        self.store, self.run_id, self.token = store, run_id, token

    def message(self, message: str) -> None:
        if self.token:
            message = message.replace(self.token, "[redacted]")
        self.store.event(self.run_id, message)


def execute(store: AppStore, run_id: str, owner: str, parent_pid: int, reserve_bytes: int) -> None:
    run = store.run(run_id)
    city = store.city(run["city_id"])
    city_dir = store.city_dir(run["city_id"])
    token = os.getenv("COMPRAS_GOV_TOKEN")
    reporter = Reporter(store, run_id, token)
    control = WorkerControl(store, run_id, owner, parent_pid, reserve_bytes)
    try:
        lock = file_lock(city_dir / "writer.lock")
        lock.__enter__()
    except RuntimeError:
        store.update_run(run_id, owner, "queued", error="aguardando liberação do worker anterior", delay=5)
        return
    try:
        control.check()
        params = run["config"]
        config = FullCityConfig(
            db_path=city_dir / "data", bronze_db_path=city_dir / "bronze.duckdb", ops_db_path=city_dir / "ops.sqlite",
            municipality_code=int(city["id"]), state_uf=city["uf"], token=token,
            start_date=params["start_date"], end_date=params["end_date"], collection_id=run_id,
            max_pages_per_job=params.get("max_pages_per_job", 500),
            max_purchases=params.get("max_purchases", 0), max_units=params.get("max_units", 0),
            max_suppliers=0, max_price_items=0,
        )
        result = FullCityCrawler(config, reporter=reporter, control=control,
                                 throttle=SharedThrottle(store, control)).run()
        control.check()
        if not store.start_projection(run_id, owner):
            raise CrawlStopped("parada solicitada antes da publicação")
        reporter.message("Publicando projeção consistente; a versão anterior continua disponível.")
        summary = build_snapshot(store, city["id"], coverage=dict(
            status="partial" if result.errors else "complete", run_id=run_id,
            message="Coleta com falhas; dados anteriores podem estar preservados." if result.errors else "Execução concluída sem falhas definitivas; cobertura limitada ao recorte solicitado.",
            start_date=config.start_date, end_date=config.end_date,
            errors=list(result.errors), skipped=list(result.skipped_operations),
        ), before_publish=control.check, publication_lease=(run_id, owner))
        report = dict(run_id=result.run_id, stats=result.stats, errors=list(result.errors),
                      skipped=list(result.skipped_operations), coverage=summary)
        store.update_run(run_id, owner, "partial" if result.errors else "finished", result=report)
        reporter.message("Projeção publicada. " + ("Há falhas definitivas a revisar." if result.errors else "Coleta finalizada."))
    except CrawlStopped as exc:
        status = "stopped" if store.run(run_id)["status"] == "stopping" else "interrupted"
        store.update_run(run_id, owner, status)
        reporter.message(str(exc) or "Coleta interrompida; páginas confirmadas preservadas.")
    except Exception as exc:
        message = str(exc)
        if token:
            message = message.replace(token, "[redacted]")
        store.update_run(run_id, owner, "failed", error=message[:2000])
        reporter.message("Falha: " + message[:2000])
    finally:
        lock.__exit__(None, None, None)


if __name__ == "__main__":
    execute(AppStore(Path(sys.argv[1])), sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
