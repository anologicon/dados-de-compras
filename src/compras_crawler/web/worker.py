"""Isolated city worker. Invoked by the local service, never by HTTP parameters."""
from __future__ import annotations

from pathlib import Path
import os
import re
import sys

from ..crawl_state import CrawlStopped
from ..full_city import FullCityConfig, FullCityCrawler
from ..pncp_direct import PncpDirectCollector, PncpDirectConfig
from .analytics import build_snapshot
from .runtime import SharedThrottle, WorkerControl, file_lock
from .store import AppStore


def stage_coverage(source, stats, errors):
    prefixes = {
        "pncp_direct": ("pncp_direto_listagem", "pncp_direto_itens_", "pncp_direto_resultados_"),
        "comprasgov": ("pncp_contratacoes_", "pncp_itens_", "pncp_resultados_"),
    }
    stages = {}
    fanout_job = "fanout_limit" if source == "pncp_direct" else "pncp_purchase_fanout_limit"
    for stage, prefix in zip(("listing", "items", "results"), prefixes[source]):
        jobs = [counts for name, counts in stats.items() if name.startswith(prefix)]
        pages = sum(job.get("pages", 0) for job in jobs)
        records = sum(job.get("records", 0) for job in jobs)
        failures = [error["message"] for error in errors if str(error.get("job_name", "")).startswith(prefix)
                    or (stage == "items" and str(error.get("job_name", "")).startswith("pncp_direto_quantidade_itens_"))
                    or (stage == "listing" and error.get("job_name") == "pncp_direto_modalidades")
                    or (stage != "listing" and error.get("job_name") == fanout_job)]
        if failures:
            unavailable = not pages and all(re.search(r"\bHTTP (?:401|403|429|5\d\d)\b", msg) for msg in failures)
            status = "unavailable" if unavailable else "error"
        else:
            status = ("complete" if records else "empty") if pages else "not_collected"
        stages[stage] = dict(status=status, pages=pages, records=records)
    if stages["listing"]["status"] in ("error", "unavailable"):
        for stage in ("items", "results"):
            if stages[stage]["status"] in ("complete", "empty"):
                stages[stage]["status"] = "partial"
    return stages


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
        common = dict(
            db_path=city_dir / "data", bronze_db_path=city_dir / "bronze.duckdb", ops_db_path=city_dir / "ops.sqlite",
            municipality_code=int(city["id"]), state_uf=city["uf"],
            start_date=params["start_date"], end_date=params["end_date"], collection_id=run_id,
            max_pages_per_job=params.get("max_pages_per_job", 500),
            max_purchases=params.get("max_purchases", 0),
        )
        selected = params.get("collection_sources", ["comprasgov"])
        throttle = SharedThrottle(store, control)
        sources = {}
        window = dict(start_date=common["start_date"], end_date=common["end_date"])
        errors, skipped, stats = [], [], {}
        for source in ("pncp_direct", "comprasgov"):
            if source not in selected:
                sources[source] = dict(status="not_selected", **window)
                continue
            control.check()
            if source == "pncp_direct":
                collector = PncpDirectCollector(PncpDirectConfig(**common),
                                                reporter=reporter, control=control, throttle=throttle)
            else:
                collector = FullCityCrawler(FullCityConfig(
                    **common, token=token, max_units=params.get("max_units", 0),
                    max_suppliers=0, max_price_items=0,
                ), reporter=reporter, control=control, throttle=throttle)
            result = collector.run()
            sources[source] = dict(status="partial" if result.errors else "complete",
                                   run_id=result.run_id, stats=result.stats, **window,
                                   stages=stage_coverage(source, result.stats, result.errors))
            errors.extend(dict(error, source=source) for error in result.errors)
            skipped.extend(getattr(result, "skipped_operations", ()))
            stats.update(result.stats)
        control.check()
        if not store.start_projection(run_id, owner):
            raise CrawlStopped("parada solicitada antes da publicação")
        reporter.message("Publicando projeção consistente; a versão anterior continua disponível.")
        summary = build_snapshot(store, city["id"], coverage=dict(
            status="partial" if errors else "complete", run_id=run_id,
            message="Coleta com falhas; dados anteriores podem estar preservados." if errors else "Execução concluída sem falhas definitivas; cobertura limitada ao recorte solicitado.",
            start_date=common["start_date"], end_date=common["end_date"],
            errors=errors, skipped=skipped, sources=sources, prior_snapshot=bool(city["snapshot"]),
        ), before_publish=control.check, publication_lease=(run_id, owner))
        report = dict(run_id=result.run_id if len(selected) == 1 else run_id,
                      stats=stats, errors=errors, skipped=skipped, coverage=summary)
        store.update_run(run_id, owner, "partial" if errors else "finished", result=report)
        reporter.message("Projeção publicada. " + ("Há falhas definitivas a revisar." if errors else "Coleta finalizada."))
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
