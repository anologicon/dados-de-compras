from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from .client import ComprasClient, validate_base_url
from .log import get_logger
from .manifest import EndpointJob, build_historical_manifest, default_date_window
from .ui import RunContext
from .normalize import extract_records, normalize_records, stable_hash, stable_json
from .storage import DuckWarehouse


@dataclass(frozen=True)
class SyncConfig:
    db_path: Path
    base_url: str = "https://dadosabertos.compras.gov.br"
    token: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    page_size: int | None = None
    endpoints: tuple[str, ...] = ()
    resume: bool = True
    scope: str = "historical"
    state_uf: str | None = None
    municipality_code: int | None = None
    pncp_modalidade_code: int | None = None

    def __post_init__(self) -> None:
        validate_base_url(self.base_url, token=self.token)
        if self.state_uf is not None:
            object.__setattr__(self, "state_uf", self.state_uf.strip().upper())
            if len(self.state_uf) != 2:
                raise ValueError("state_uf must be a 2-letter UF abbreviation")
        pncp_selected = "consultarContratacoes_PNCP_14133" in self.endpoints
        if self.municipality_code is not None:
            if self.state_uf is None:
                raise ValueError("municipality_code requires state_uf")
            if not pncp_selected:
                raise ValueError("municipality_code requires operation consultarContratacoes_PNCP_14133")
            if self.pncp_modalidade_code is None:
                raise ValueError("municipality_code requires pncp_modalidade_code")
        if self.pncp_modalidade_code is not None and not pncp_selected:
            raise ValueError("pncp_modalidade_code requires operation consultarContratacoes_PNCP_14133")

    def resolved_dates(self) -> tuple[str, str]:
        if self.start_date and self.end_date:
            return self.start_date, self.end_date
        return default_date_window()


class SyncRunner:
    def __init__(
        self,
        *,
        config: SyncConfig,
        client: ComprasClient | Any | None = None,
        jobs: tuple[EndpointJob, ...] | None = None,
        reporter: Any | None = None,
    ):
        self.config = config
        self.client = client or ComprasClient(config.base_url, token=config.token)
        start_date, end_date = config.resolved_dates()
        self.jobs = jobs or build_historical_manifest(
            start_date,
            end_date,
            page_size=config.page_size,
            endpoints=config.endpoints or None,
            state_uf=config.state_uf,
            municipality_code=config.municipality_code,
            pncp_modalidade_code=config.pncp_modalidade_code,
        )
        self.warehouse = DuckWarehouse(config.db_path)
        self.logger = get_logger("sync")
        self.reporter = reporter

    def run(self) -> str:
        self.warehouse.init_schema()
        run_id = self.warehouse.start_run(base_url=self.config.base_url, scope=self.config.scope)
        self._notify(
            "start",
            ctx=RunContext(
                run_id=run_id,
                db_path=self.config.db_path,
                base_url=self.config.base_url,
                scope=self.config.scope,
                start_date=self.config.start_date,
                end_date=self.config.end_date,
                page_size=self.config.page_size,
                resume=self.config.resume,
                total_jobs=len(self.jobs),
            ),
        )
        self.logger.info(
            "run started run_id=%s base_url=%s scope=%s jobs=%d",
            run_id,
            self.config.base_url,
            self.config.scope,
            len(self.jobs),
        )
        try:
            for index, job in enumerate(self.jobs, start=1):
                self._run_job(run_id, job, index=index, total=len(self.jobs))
            self.warehouse.finish_run(run_id, status="finished")
            self.logger.info("run finished run_id=%s status=finished", run_id)
            self._notify("run_finished", run_id=run_id, status="finished")
            return run_id
        except Exception as exc:
            self.logger.exception(
                "run failed run_id=%s job=%s page=%s",
                run_id,
                getattr(exc, "job_name", "sync"),
                getattr(exc, "page_number", None),
            )
            self.warehouse.record_error(
                run_id=run_id,
                job_name=getattr(exc, "job_name", "sync"),
                page_number=getattr(exc, "page_number", None),
                message=str(exc),
                payload_json=None,
            )
            self.warehouse.finish_run(run_id, status="failed")
            self._notify(
                "run_failed",
                run_id=run_id,
                job_name=getattr(exc, "job_name", "sync"),
                page_number=getattr(exc, "page_number", None),
                message=str(exc),
            )
            raise

    def _run_job(self, run_id: str, job: EndpointJob, *, index: int, total: int) -> None:
        start_page = self.warehouse.load_checkpoint(job.name) if self.config.resume else None
        page = start_page or 1
        self._notify(
            "job_started",
            index=index,
            total=total,
            job_name=job.name,
            entity_name=job.entity_name,
            path=job.path,
            start_page=page,
            resume=self.config.resume,
        )
        self.logger.info(
            "job started run_id=%s job=%s entity=%s path=%s start_page=%s resume=%s",
            run_id,
            job.name,
            job.entity_name,
            job.path,
            page,
            self.config.resume,
        )

        if hasattr(self.client, "fetch_page"):
            while True:
                request_params = self._page_params(job, page)
                self._notify("fetch_started", job_name=job.name, page_number=page, path=job.path)
                fetch_started = monotonic()
                page_data = self.client.fetch_page(job.path, request_params, accept=job.accept)
                fetch_elapsed = monotonic() - fetch_started
                record_count = len(page_data.records)
                self._notify(
                    "fetch_finished",
                    job_name=job.name,
                    page_number=page_data.page_number,
                    status_code=page_data.status_code,
                    elapsed_seconds=fetch_elapsed,
                    record_count=record_count,
                    content_type=page_data.content_type or job.accept,
                )
                self.warehouse.land_page(
                    run_id=run_id,
                    job_name=job.name,
                    entity_name=job.entity_name,
                    page_number=page_data.page_number,
                    request_params_json=stable_json(page_data.params),
                    response_format=page_data.content_type or job.accept,
                    http_status=page_data.status_code,
                    payload_json=stable_json(page_data.raw),
                    payload_text=page_data.raw if isinstance(page_data.raw, str) else None,
                    payload_hash=stable_hash(page_data.raw),
                )
                normalized = normalize_records(
                    entity_name=job.entity_name,
                    records=extract_records(page_data.raw) if not page_data.records else page_data.records,
                    key_fields=job.key_fields,
                    run_id=run_id,
                    source_job=job.name,
                    source_page=page_data.page_number,
                )
                self.warehouse.upsert_records(normalized)
                self.warehouse.save_checkpoint(job.name, next_page=page_data.page_number + 1, payload_hash=stable_hash(page_data.raw))
                self._notify(
                    "page_done",
                    job_name=job.name,
                    page_number=page_data.page_number,
                    status_code=page_data.status_code,
                    record_count=len(normalized),
                )
                self.logger.info(
                    "job page done run_id=%s job=%s page=%s status=%s records=%s",
                    run_id,
                    job.name,
                    page_data.page_number,
                    page_data.status_code,
                    len(normalized),
                )
                page = page_data.page_number + 1
                if not self._should_continue(page_data, job.accept):
                    break
        else:
            for page_data in self.client.iter_pages(job.path, self._page_params(job, page), accept=job.accept, job_name=job.name):
                self.warehouse.land_page(
                    run_id=run_id,
                    job_name=job.name,
                    entity_name=job.entity_name,
                    page_number=page_data.page_number,
                    request_params_json=stable_json(page_data.params),
                    response_format=page_data.content_type or job.accept,
                    http_status=page_data.status_code,
                    payload_json=stable_json(page_data.raw),
                    payload_text=page_data.raw if isinstance(page_data.raw, str) else None,
                    payload_hash=stable_hash(page_data.raw),
                )
                normalized = normalize_records(
                    entity_name=job.entity_name,
                    records=extract_records(page_data.raw) if not page_data.records else page_data.records,
                    key_fields=job.key_fields,
                    run_id=run_id,
                    source_job=job.name,
                    source_page=page_data.page_number,
                )
                self.warehouse.upsert_records(normalized)
                self.warehouse.save_checkpoint(job.name, next_page=page_data.page_number + 1, payload_hash=stable_hash(page_data.raw))
                self._notify(
                    "page_done",
                    job_name=job.name,
                    page_number=page_data.page_number,
                    status_code=page_data.status_code,
                    record_count=len(normalized),
                )
                self.logger.info(
                    "job page done run_id=%s job=%s page=%s status=%s records=%s",
                    run_id,
                    job.name,
                    page_data.page_number,
                    page_data.status_code,
                    len(normalized),
                )
                page = page_data.page_number + 1
        self._notify("job_finished", job_name=job.name, next_page=page)
        self.logger.info("job finished run_id=%s job=%s next_page=%s", run_id, job.name, page)

    def _notify(self, event: str, /, **kwargs: Any) -> None:
        if not self.reporter:
            return
        handler = getattr(self.reporter, event, None)
        if handler:
            handler(**kwargs)

    def _should_continue(self, page_data, accept: str) -> bool:
        if accept == "csv":
            return bool(page_data.records)
        if isinstance(page_data.raw, dict) and int(page_data.raw.get("paginasRestantes", 0) or 0) > 0:
            return True
        return bool(page_data.records)

    def _page_params(self, job: EndpointJob, page: int) -> dict[str, Any]:
        params = dict(job.base_params)
        params["pagina"] = page
        return params


def build_runner(config: SyncConfig, reporter: Any | None = None) -> SyncRunner:
    return SyncRunner(config=config, reporter=reporter)
