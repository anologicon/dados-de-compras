from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any
import asyncio
import inspect

from .client import AsyncComprasClient, ComprasClient, validate_base_url
from .log import get_logger
from .manifest import EndpointJob, build_historical_manifest, build_municipality_purchase_manifest, default_date_window
from .ui import RunContext
from .normalize import stable_hash, stable_json
from .storage import DEFAULT_DB_PREFIX, DuckWarehouse, SqliteOpsStore, derive_bronze_db_path, derive_ops_db_path


def _supports_keyword(callable_obj: Any, keyword: str) -> bool:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False
    return keyword in signature.parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
    )


@dataclass(frozen=True)
class SyncConfig:
    db_path: Path = DEFAULT_DB_PREFIX
    ops_db_path: Path | None = None
    bronze_db_path: Path | None = None
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
    pncp_modalidade_codes: tuple[int, ...] = ()
    purchase_sources: tuple[str, ...] = ()
    async_mode: bool = False
    concurrency: int = 5
    delay_seconds: float = 1.0
    rate_limit_sleep_seconds: float = 60.0
    request_timeout: float = 45.0
    request_retries: int = 5
    retry_backoff_seconds: float = 2.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "db_path", Path(self.db_path))
        object.__setattr__(self, "bronze_db_path", Path(self.bronze_db_path) if self.bronze_db_path is not None else derive_bronze_db_path(self.db_path))
        object.__setattr__(self, "ops_db_path", Path(self.ops_db_path) if self.ops_db_path is not None else derive_ops_db_path(self.db_path))

        validate_base_url(self.base_url, token=self.token)
        if self.concurrency < 1:
            raise ValueError("concurrency must be greater than or equal to 1")
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        if self.rate_limit_sleep_seconds < 0:
            raise ValueError("rate_limit_sleep_seconds must be non-negative")
        if self.request_timeout <= 0:
            raise ValueError("request_timeout must be positive")
        if self.request_retries < 0:
            raise ValueError("request_retries must be non-negative")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")

        if self.state_uf is not None:
            object.__setattr__(self, "state_uf", self.state_uf.strip().upper())
            if len(self.state_uf) != 2:
                raise ValueError("state_uf must be a 2-letter UF abbreviation")

        sources: list[str] = []
        seen_sources: set[str] = set()
        for source in self.purchase_sources:
            normalized = source.strip().lower()
            if not normalized or normalized in seen_sources:
                continue
            sources.append(normalized)
            seen_sources.add(normalized)
        object.__setattr__(self, "purchase_sources", tuple(sources))

        codes = tuple(self.pncp_modalidade_codes)
        if not codes and self.pncp_modalidade_code is not None:
            codes = (self.pncp_modalidade_code,)
        elif codes and self.pncp_modalidade_code is not None and self.pncp_modalidade_code not in codes:
            codes = (self.pncp_modalidade_code, *codes)
        object.__setattr__(self, "pncp_modalidade_codes", codes)
        object.__setattr__(self, "pncp_modalidade_code", codes[0] if codes else None)

        if self.purchase_sources and self.endpoints:
            raise ValueError("purchase_sources cannot be combined with endpoints")

        city_mode = bool(self.purchase_sources) or (self.municipality_code is not None and not self.endpoints)
        pncp_selected = "consultarContratacoes_PNCP_14133" in self.endpoints

        if self.municipality_code is not None:
            if self.state_uf is None:
                raise ValueError("municipality_code requires state_uf")
            if city_mode:
                if not self.purchase_sources:
                    object.__setattr__(self, "purchase_sources", ("pncp",))
                if not self.pncp_modalidade_codes:
                    raise ValueError("municipality_code requires pncp_modalidade_code")
            else:
                if self.pncp_modalidade_codes and not pncp_selected:
                    raise ValueError("pncp_modalidade_code requires operation consultarContratacoes_PNCP_14133")
                if pncp_selected and not self.pncp_modalidade_codes:
                    raise ValueError("consultarContratacoes_PNCP_14133 requires pncp_modalidade_code")
        elif self.purchase_sources:
            raise ValueError("purchase_sources requires municipality_code")

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
        self.client = client or ComprasClient(
            config.base_url,
            token=config.token,
            timeout=config.request_timeout,
            max_retries=config.request_retries,
            retry_backoff_seconds=config.retry_backoff_seconds,
            rate_limit_sleep_seconds=config.rate_limit_sleep_seconds,
            request_interval_seconds=config.delay_seconds,
        )
        self.jobs = jobs or build_jobs_for_config(config)
        self.warehouse = DuckWarehouse(config.bronze_db_path)
        self.ops_store = SqliteOpsStore(config.ops_db_path)
        self.logger = get_logger("sync")
        self.reporter = reporter

    def run(self) -> str:
        self.warehouse.init_schema()
        self.ops_store.init_schema()
        run_id = self.ops_store.start_run(
            base_url=self.config.base_url,
            scope=self.config.scope,
            data_db_path=self.config.db_path,
            bronze_db_path=self.config.bronze_db_path,
        )
        self._notify(
            "start",
            ctx=RunContext(
                run_id=run_id,
                bronze_db_path=self.config.bronze_db_path,
                ops_db_path=self.config.ops_db_path,
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
            self.ops_store.finish_run(run_id, status="finished")
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
            self.ops_store.record_error(
                run_id=run_id,
                job_name=getattr(exc, "job_name", "sync"),
                page_number=getattr(exc, "page_number", None),
                message=str(exc),
                payload_json=None,
            )
            self.ops_store.finish_run(run_id, status="failed")
            self._notify(
                "run_failed",
                run_id=run_id,
                job_name=getattr(exc, "job_name", "sync"),
                page_number=getattr(exc, "page_number", None),
                message=str(exc),
            )
            raise

    def _run_job(self, run_id: str, job: EndpointJob, *, index: int, total: int) -> None:
        start_page = self.ops_store.load_checkpoint(job.name) if self.config.resume else None
        page = start_page or 1
        self._notify_job_started(run_id, job, index=index, total=total, start_page=page)

        if hasattr(self.client, "fetch_page"):
            while True:
                page_data = self._fetch_page_with_reporting(job, page)
                self._persist_page(run_id, job, page_data)
                page = page_data.page_number + 1
                if not self._should_continue(page_data, job.accept):
                    break
        else:
            iter_pages = getattr(self.client, "iter_pages")
            kwargs: dict[str, Any] = {"accept": job.accept, "job_name": job.name}
            if _supports_keyword(iter_pages, "use_auth"):
                kwargs["use_auth"] = job.requires_auth
            elif job.requires_auth:
                raise TypeError("authenticated jobs require a client iter_pages method that accepts use_auth")
            for page_data in iter_pages(job.path, self._page_params(job, page), **kwargs):
                self._persist_page(run_id, job, page_data)
                page = page_data.page_number + 1
        self._notify("job_finished", job_name=job.name, next_page=page)
        self.logger.info("job finished run_id=%s job=%s next_page=%s", run_id, job.name, page)

    def _notify_job_started(self, run_id: str, job: EndpointJob, *, index: int, total: int, start_page: int) -> None:
        self._notify(
            "job_started",
            index=index,
            total=total,
            job_name=job.name,
            entity_name=job.entity_name,
            path=job.path,
            start_page=start_page,
            resume=self.config.resume,
        )
        self.logger.info(
            "job started run_id=%s job=%s entity=%s path=%s start_page=%s resume=%s",
            run_id,
            job.name,
            job.entity_name,
            job.path,
            start_page,
            self.config.resume,
        )

    def _fetch_page_with_reporting(self, job: EndpointJob, page: int):
        request_params = self._page_params(job, page)
        self._notify("fetch_started", job_name=job.name, page_number=page, path=job.path)
        fetch_started = monotonic()
        try:
            page_data = self._call_fetch_page_sync(job.path, request_params, accept=job.accept, use_auth=job.requires_auth)
        except Exception as exc:
            setattr(exc, "job_name", job.name)
            setattr(exc, "page_number", page)
            raise
        self._notify_fetch_finished(job, page_data, elapsed_seconds=monotonic() - fetch_started)
        return page_data

    def _call_fetch_page_sync(self, path: str, params: dict[str, Any], *, accept: str, use_auth: bool):
        fetch_page = getattr(self.client, "fetch_page")
        if _supports_keyword(fetch_page, "use_auth"):
            return fetch_page(path, params, accept=accept, use_auth=use_auth)
        if use_auth:
            raise TypeError("authenticated jobs require a client fetch_page method that accepts use_auth")
        return fetch_page(path, params, accept=accept)

    def _notify_fetch_finished(self, job: EndpointJob, page_data, *, elapsed_seconds: float) -> None:
        self._notify(
            "fetch_finished",
            job_name=job.name,
            page_number=page_data.page_number,
            status_code=page_data.status_code,
            elapsed_seconds=elapsed_seconds,
            record_count=len(page_data.records),
            content_type=page_data.content_type or job.accept,
        )

    def _persist_page(self, run_id: str, job: EndpointJob, page_data) -> int:
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
        record_count = len(page_data.records)
        self.ops_store.save_checkpoint(job.name, next_page=page_data.page_number + 1, payload_hash=stable_hash(page_data.raw))
        self._notify(
            "page_done",
            job_name=job.name,
            page_number=page_data.page_number,
            status_code=page_data.status_code,
            record_count=record_count,
        )
        self.logger.info(
            "job page done run_id=%s job=%s page=%s status=%s records=%s",
            run_id,
            job.name,
            page_data.page_number,
            page_data.status_code,
            record_count,
        )
        return record_count

    def _notify(self, event: str, /, **kwargs: Any) -> None:
        if not self.reporter:
            return
        handler = getattr(self.reporter, event, None)
        if handler:
            handler(**kwargs)

    def _should_continue(self, page_data, accept: str) -> bool:
        if accept == "csv":
            return bool(page_data.records)
        if isinstance(page_data.raw, dict):
            if "paginasRestantes" in page_data.raw:
                return int(page_data.raw.get("paginasRestantes") or 0) > 0
            if "totalPaginas" in page_data.raw:
                return page_data.page_number < int(page_data.raw.get("totalPaginas") or 0)
        return bool(page_data.records)

    def _page_params(self, job: EndpointJob, page: int) -> dict[str, Any]:
        params = dict(job.base_params)
        params["pagina"] = page
        return params


class AsyncSyncRunner(SyncRunner):
    """Concurrent page fetch runner with serial DuckDB writes."""

    def __init__(
        self,
        *,
        config: SyncConfig,
        client: AsyncComprasClient | ComprasClient | Any | None = None,
        jobs: tuple[EndpointJob, ...] | None = None,
        reporter: Any | None = None,
    ):
        super().__init__(
            config=config,
            client=client
            or AsyncComprasClient(
                config.base_url,
                token=config.token,
                timeout=config.request_timeout,
                max_retries=config.request_retries,
                retry_backoff_seconds=config.retry_backoff_seconds,
                rate_limit_sleep_seconds=config.rate_limit_sleep_seconds,
                request_interval_seconds=config.delay_seconds,
            ),
            jobs=jobs,
            reporter=reporter,
        )

    def run(self) -> str:
        return asyncio.run(self.run_async())

    async def run_async(self) -> str:
        self.warehouse.init_schema()
        self.ops_store.init_schema()
        run_id = self.ops_store.start_run(
            base_url=self.config.base_url,
            scope=self.config.scope,
            data_db_path=self.config.db_path,
            bronze_db_path=self.config.bronze_db_path,
        )
        self._notify(
            "start",
            ctx=RunContext(
                run_id=run_id,
                bronze_db_path=self.config.bronze_db_path,
                ops_db_path=self.config.ops_db_path,
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
            "async run started run_id=%s base_url=%s scope=%s jobs=%d concurrency=%d delay_seconds=%.3f",
            run_id,
            self.config.base_url,
            self.config.scope,
            len(self.jobs),
            self.config.concurrency,
            self.config.delay_seconds,
        )
        try:
            for index, job in enumerate(self.jobs, start=1):
                await self._run_job_async(run_id, job, index=index, total=len(self.jobs))
            self.ops_store.finish_run(run_id, status="finished")
            self.logger.info("async run finished run_id=%s status=finished", run_id)
            self._notify("run_finished", run_id=run_id, status="finished")
            return run_id
        except Exception as exc:
            self.logger.exception(
                "async run failed run_id=%s job=%s page=%s",
                run_id,
                getattr(exc, "job_name", "sync"),
                getattr(exc, "page_number", None),
            )
            self.ops_store.record_error(
                run_id=run_id,
                job_name=getattr(exc, "job_name", "sync"),
                page_number=getattr(exc, "page_number", None),
                message=str(exc),
                payload_json=None,
            )
            self.ops_store.finish_run(run_id, status="failed")
            self._notify(
                "run_failed",
                run_id=run_id,
                job_name=getattr(exc, "job_name", "sync"),
                page_number=getattr(exc, "page_number", None),
                message=str(exc),
            )
            raise

    async def _run_job_async(self, run_id: str, job: EndpointJob, *, index: int, total: int) -> None:
        start_page = self.ops_store.load_checkpoint(job.name) if self.config.resume else None
        page = start_page or 1
        self._notify_job_started(run_id, job, index=index, total=total, start_page=page)

        first_page = await self._fetch_page_with_reporting_async(job, page)
        self._persist_page(run_id, job, first_page)
        page = first_page.page_number + 1

        if self._should_continue(first_page, job.accept):
            last_page = self._known_last_page(first_page, job.accept)
            if last_page is None:
                page = await self._run_remaining_pages_sequential_async(run_id, job, page)
            else:
                page = await self._run_remaining_pages_concurrent_async(run_id, job, page, last_page)

        self._notify("job_finished", job_name=job.name, next_page=page)
        self.logger.info("async job finished run_id=%s job=%s next_page=%s", run_id, job.name, page)

    async def _run_remaining_pages_sequential_async(self, run_id: str, job: EndpointJob, page: int) -> int:
        while True:
            page_data = await self._fetch_page_with_reporting_async(job, page)
            self._persist_page(run_id, job, page_data)
            page = page_data.page_number + 1
            if not self._should_continue(page_data, job.accept):
                return page

    async def _run_remaining_pages_concurrent_async(self, run_id: str, job: EndpointJob, page: int, last_page: int) -> int:
        concurrency = max(1, self.config.concurrency)
        while page <= last_page:
            batch_end = min(last_page, page + concurrency - 1)
            page_batch = range(page, batch_end + 1)
            pages = await asyncio.gather(*(self._fetch_page_with_reporting_async(job, page_number) for page_number in page_batch))
            for page_data in sorted(pages, key=lambda item: item.page_number):
                self._persist_page(run_id, job, page_data)
                page = page_data.page_number + 1
        return page

    async def _fetch_page_with_reporting_async(self, job: EndpointJob, page: int):
        request_params = self._page_params(job, page)
        self._notify("fetch_started", job_name=job.name, page_number=page, path=job.path)
        fetch_started = monotonic()
        try:
            page_data = await self._call_fetch_page_async(job.path, request_params, accept=job.accept, use_auth=job.requires_auth)
        except Exception as exc:
            setattr(exc, "job_name", job.name)
            setattr(exc, "page_number", page)
            raise
        self._notify_fetch_finished(job, page_data, elapsed_seconds=monotonic() - fetch_started)
        return page_data

    async def _call_fetch_page_async(self, path: str, params: dict[str, Any], *, accept: str, use_auth: bool):
        fetch_page = getattr(self.client, "fetch_page", None)
        if fetch_page is None:
            raise TypeError("async sync requires a client with fetch_page")
        kwargs: dict[str, Any] = {"accept": accept}
        if _supports_keyword(fetch_page, "use_auth"):
            kwargs["use_auth"] = use_auth
        elif use_auth:
            raise TypeError("authenticated jobs require a client fetch_page method that accepts use_auth")
        if inspect.iscoroutinefunction(fetch_page):
            return await fetch_page(path, params, **kwargs)
        return await asyncio.to_thread(fetch_page, path, params, **kwargs)

    def _known_last_page(self, page_data, accept: str) -> int | None:
        if accept == "csv" or not isinstance(page_data.raw, dict):
            return None
        if "totalPaginas" in page_data.raw:
            total = int(page_data.raw.get("totalPaginas") or 0)
            return total if total >= page_data.page_number else page_data.page_number
        if "paginasRestantes" in page_data.raw:
            return page_data.page_number + int(page_data.raw.get("paginasRestantes") or 0)
        return None


def build_jobs_for_config(config: SyncConfig) -> tuple[EndpointJob, ...]:
    start_date, end_date = config.resolved_dates()
    if config.purchase_sources:
        return build_municipality_purchase_manifest(
            start_date,
            end_date,
            municipality_code=config.municipality_code,
            state_uf=config.state_uf,
            sources=config.purchase_sources,
            pncp_modalidade_codes=config.pncp_modalidade_codes,
            page_size=config.page_size,
        )
    return build_historical_manifest(
        start_date,
        end_date,
        page_size=config.page_size,
        endpoints=config.endpoints or None,
        state_uf=config.state_uf,
        municipality_code=config.municipality_code,
        pncp_modalidade_codes=config.pncp_modalidade_codes,
    )


def build_runner(config: SyncConfig, reporter: Any | None = None) -> SyncRunner:
    if config.async_mode:
        return AsyncSyncRunner(config=config, reporter=reporter)
    return SyncRunner(config=config, reporter=reporter)
