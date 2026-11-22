"""PNCP direct source: durable client and municipal collector.

Implemented per docs/PNCP_DIRECT_PLAN.md. Deliberately separate from the
Compras.gov.br ``FullCityCrawler``: fixed HTTPS hosts with strict path
validation, no authentication at all (never sends ``COMPRAS_GOV_TOKEN``), PNCP
pagination rules (page size 50/minimum 10, HTTP 204 valid, children returned as
arrays, operation-specific parsing) while reusing shared stop control, disk
reserve, throttling and transactional crawl-state persistence.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urlparse
import re

import requests

from .client import DEFAULT_RETRY_STATUS_CODES, PageData, RequestThrottle, retry_after_seconds
from .crawl_state import CrawlDiskReserve, CrawlState, CrawlStopped
from .full_city import first_present, sanitize
from .normalize import stable_hash, stable_json
from .storage import DEFAULT_DB_PREFIX, BronzeWarehouse, SqliteOpsStore, derive_bronze_db_path, derive_ops_db_path

PNCP_HOST = "pncp.gov.br"
PNCP_CONSULTA_BASE = f"https://{PNCP_HOST}/api/consulta/v1"
PNCP_PNCP_BASE = f"https://{PNCP_HOST}/api/pncp/v1"
PNCP_CONTRACT_VERSION = "v1-2026-10-26"
SOURCE_NAME = "pncp_direct"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50

ENTITY_PURCHASE = "pncp_direct_contratacao"
ENTITY_ITEM = "pncp_direct_item_contratacao"
ENTITY_RESULT = "pncp_direct_resultado_item"
ENTITY_MODALITY = "pncp_direct_modalidade"

CONTROL_PATTERN = r"^(\d{14})-(\d+)-(\d+)/(\d{4})$"


def validate_pncp_url(url: str) -> None:
    """Only fixed HTTPS hosts and documented PNCP API path roots are allowed."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if scheme != "https":
        raise ValueError("PNCP urls must use https://")
    if not parsed.netloc or not hostname:
        raise ValueError("PNCP url must include a host")
    if hostname != PNCP_HOST:
        raise ValueError(f"PNCP collection is restricted to https://{PNCP_HOST}")
    if parsed.port not in (None, 443):
        raise ValueError("PNCP collection must use the default https port")
    if parsed.username or parsed.password:
        raise ValueError("PNCP url must not include credentials")
    if parsed.fragment:
        raise ValueError("PNCP url must not include a fragment")
    if parsed.query:
        raise ValueError("PNCP url must not include a query string")
    allowed_roots = ("/api/consulta/v1/", "/api/pncp/v1/")
    if not any(path == root.rstrip("/") or path.startswith(root) for root in allowed_roots):
        raise ValueError("PNCP path is outside the documented public API roots")


def _is_pncp_url(url: str) -> bool:
    try:
        validate_pncp_url(url)
    except ValueError:
        return False
    return True


def parse_pncp_control(value: Any) -> dict[str, Any] | None:
    """Parse ``cnpj-segmento-sequencial/ano`` control numbers; None when unparseable.

    Unparseable controls keep their identity as the raw string but cannot be
    structurally cross-checked; contradictions, not parse failures, are ambiguity.
    """
    match = re.match(CONTROL_PATTERN, str(value).strip())
    if not match:
        return None
    return {
        "cnpj": match.group(1),
        "segmento": int(match.group(2)),
        "sequencial": int(match.group(3)),
        "ano": int(match.group(4)),
    }


def nested_first(row: dict[str, Any], *paths: Any) -> Any:
    """Read the first present value from flattened or nested (>caminho>) paths."""
    for path in paths:
        if isinstance(path, tuple):
            value: Any = row
            for step in path:
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(step)
            if value not in (None, ""):
                return value
            continue
        value = row.get(path)
        if value not in (None, ""):
            return value
    return None


def control_incoherence(control: Any, row: dict[str, Any]) -> list[str]:
    """Explicit divergence between the control number and the purchase body."""
    parts = parse_pncp_control(control)
    if parts is None:
        return []
    problems: list[str] = []
    cnpj = str(nested_first(row, ("orgaoEntidade", "cnpj"), "orgaoEntidadeCnpj") or "")
    if cnpj.strip() and cnpj != parts["cnpj"]:
        problems.append(f"numeroControlePNCP cnpj {parts['cnpj']} diverges from body cnpj {cnpj}")
    year = nested_first(row, "anoCompra")
    if year is not None and str(year) != str(parts["ano"]):
        problems.append(f"numeroControlePNCP year {parts['ano']} diverges from anoCompra {year}")
    sequencial = nested_first(row, "sequencialCompra")
    if sequencial is not None and str(sequencial) != str(parts["sequencial"]):
        problems.append(f"numeroControlePNCP sequencial {parts['sequencial']} diverges from sequencialCompra {sequencial}")
    return problems


def quantity_from_payload(payload: Any) -> int | None:
    """Accept the documented ``/itens/quantidade`` responses (number or dict)."""
    if isinstance(payload, bool):
        return None
    if isinstance(payload, int):
        return payload
    if isinstance(payload, dict):
        for key in ("quantidadeItens", "quantidade", "totalItens"):
            value = payload.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def supplier_identity(result: dict[str, Any]) -> dict[str, Any] | None:
    """Observed supplier identity: person type plus complete document, when compatible.

    Fornecedor values live either nested under ``fornecedor`` or flat on the row;
    both shapes are inspected without inventing identifiers.
    """
    container = result.get("fornecedor")
    nested = container if isinstance(container, dict) else {}
    person_type = nested.get("tipoPessoa")
    if person_type in (None, ""):
        person_type = result.get("tipoPessoa")
    document = nested.get("niFornecedor")
    if document in (None, ""):
        document = first_present(result, "niFornecedor", "nuDocumento")
    if person_type not in (None, "") and document not in (None, ""):
        return {"tipo": str(person_type), "documento": str(document)}
    return None


@dataclass(frozen=True)
class PncpDirectConfig:
    """Offline-default configuration for one municipality of PNCP direct collection."""

    db_path: Path = DEFAULT_DB_PREFIX
    ops_db_path: Path | None = None
    bronze_db_path: Path | None = None
    consulta_api_base: str = PNCP_CONSULTA_BASE
    pncp_api_base: str = PNCP_PNCP_BASE
    state_uf: str = "SC"
    municipality_code: int = 4202909
    start_date: str = "2026-01-01"
    end_date: str = "2026-01-31"
    modalities: tuple[int, ...] | None = None
    page_size: int = DEFAULT_PAGE_SIZE
    max_pages_per_job: int = 500
    max_purchases: int = 0
    delay_seconds: float = 1.0
    rate_limit_sleep_seconds: float = 60.0
    rate_limit_retries: int = 3
    request_timeout: float = 45.0
    request_retries: int = 5
    resume: bool = True
    collection_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "db_path", Path(self.db_path))
        object.__setattr__(
            self, "bronze_db_path",
            Path(self.bronze_db_path) if self.bronze_db_path else derive_bronze_db_path(self.db_path),
        )
        object.__setattr__(
            self, "ops_db_path",
            Path(self.ops_db_path) if self.ops_db_path else derive_ops_db_path(self.db_path),
        )
        object.__setattr__(self, "state_uf", self.state_uf.strip().upper())
        if date.fromisoformat(self.start_date) > date.fromisoformat(self.end_date):
            raise ValueError("start_date must not be after end_date")
        if len(self.state_uf) != 2:
            raise ValueError("state_uf must be a 2-letter UF abbreviation")
        if self.municipality_code <= 0:
            raise ValueError("municipality_code must be positive")
        if not MIN_PAGE_SIZE <= self.page_size <= MAX_PAGE_SIZE:
            raise ValueError(f"pncp page_size must be between {MIN_PAGE_SIZE} and {MAX_PAGE_SIZE}")
        if not _is_pncp_url(self.consulta_api_base.rstrip("/") + "/"):
            raise ValueError("consulta_api_base must be an allowed PNCP https url")
        if not _is_pncp_url(self.pncp_api_base.rstrip("/") + "/"):
            raise ValueError("pncp_api_base must be an allowed PNCP https url")
        for field_name in ("max_pages_per_job", "max_purchases", "rate_limit_retries", "request_retries"):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be greater than or equal to zero")
        if self.delay_seconds < 0 or self.rate_limit_sleep_seconds < 0 or self.request_timeout <= 0:
            raise ValueError("timeouts and delays must be non-negative, and request_timeout must be positive")
        if self.modalities is not None and not self.modalities:
            raise ValueError("modalities must either be None (fetch the published domain) or non-empty")
        object.__setattr__(self, "modalities", tuple(sorted(set(self.modalities))) if self.modalities is not None else None)


@dataclass(frozen=True)
class PncpDirectResult:
    run_id: str
    bronze_db_path: Path
    ops_db_path: Path
    stats: dict[str, dict[str, int]]
    errors: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PurchaseIdentity:
    control: str
    cnpj: str
    year: int
    sequencial: int

    @property
    def route_base(self) -> str:
        return f"/orgaos/{self.cnpj}/compras/{self.year}/{self.sequencial}"


class PncpDirectClient:
    """HTTP client for the documented public PNCP GETs.

    No authentication lives here: the token concept does not exist for this
    client, so it can never be sent, even after a 401/403. Redirects are never
    followed, so a redirect cannot silently escape the allowed host.
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        session: requests.Session | None = None,
        max_retries: int = 5,
        retry_backoff_seconds: float = 2.0,
        rate_limit_sleep_seconds: float = 60.0,
        request_interval_seconds: float = 0.0,
        throttle: RequestThrottle | None = None,
        sleep_fn: Any | None = None,
    ):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if retry_backoff_seconds < 0 or rate_limit_sleep_seconds < 0 or request_interval_seconds < 0:
            raise ValueError("retries, cooldown and interval must be non-negative")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.rate_limit_sleep_seconds = rate_limit_sleep_seconds
        self.throttle = throttle or RequestThrottle(request_interval_seconds)
        self.sleep_fn = sleep_fn

    def _headers(self) -> dict[str, str]:
        # Public consultation: never an Authorization header, from any code path.
        return {"Accept": "application/json"}

    def fetch(self, url: str, params: dict[str, Any], *, expect: str) -> PageData:
        validate_pncp_url(url)
        response = self._get_with_retries(url, params=params)
        page_number = int(params.get("pagina", 1) or 1)
        if response.status_code == 204:
            # Documented contract: 204 is a valid empty response, not invalid JSON.
            return PageData(url, page_number, dict(params), [], None, "", 204)
        response.raise_for_status()
        try:
            raw: Any = response.json()
        except ValueError as exc:
            raise ValueError(f"invalid JSON body from PNCP: {exc}") from exc
        if expect == "listing":
            records = self._listing_records(raw, url)
        elif expect == "children":
            records = self._children_records(raw, url)
        elif expect == "quantity":
            # The quantity check returns a bare number (or dict); the store keeps
            # the original payload and no synthetic record is fabricated here.
            records = []
        elif expect == "detail":
            records = self._detail_records(raw, url)
        else:  # pragma: no cover - guarded by callers
            raise ValueError(f"unknown PNCP response expectation: {expect}")
        return PageData(url, page_number, dict(params), records, raw, "application/json", response.status_code)

    def fetch_listing(self, url: str, params: dict[str, Any]) -> PageData:
        return self.fetch(url, params, expect="listing")

    def fetch_children(self, url: str, params: dict[str, Any]) -> PageData:
        return self.fetch(url, params, expect="children")

    def fetch_detail(self, url: str, params: dict[str, Any]) -> PageData:
        return self.fetch(url, params, expect="detail")

    def _listing_records(self, raw: Any, url: str) -> list[dict[str, Any]]:
        container = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(container, list):
            raise ValueError(f"PNCP listing response without a data array: {url}")
        return [row for row in container if isinstance(row, dict)]

    def _children_records(self, raw: Any, url: str) -> list[dict[str, Any]]:
        if isinstance(raw, list):
            return [row for row in raw if isinstance(row, dict)]
        raise ValueError(f"PNCP child response is not an array: {url}")

    def _detail_records(self, raw: Any, url: str) -> list[dict[str, Any]]:
        # A purchase detail must carry its own control number; error objects must
        # never be interpreted as a purchase.
        if isinstance(raw, dict) and raw.get("numeroControlePNCP"):
            return [raw]
        raise ValueError(f"PNCP detail response is not a purchase (no numeroControlePNCP): {url}")

    def _get_with_retries(self, url: str, *, params: dict[str, Any]) -> requests.Response:
        last_error: requests.RequestException | None = None
        for attempt in range(self.max_retries + 1):
            self.throttle.wait()
            try:
                response = self.session.get(url, params=params, headers=self._headers(), timeout=self.timeout, allow_redirects=False)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                self._sleep_before_retry(attempt=attempt, response=None)
                continue
            if 300 <= response.status_code < 400:
                location = response.headers.get("location", "missing")
                raise ValueError(f"PNCP redirect not followed (location={location})")
            if response.status_code not in DEFAULT_RETRY_STATUS_CODES or attempt >= self.max_retries:
                return response
            self._sleep_before_retry(attempt=attempt, response=response)
        if last_error is not None:
            raise last_error
        raise RuntimeError("request retry loop exited unexpectedly")

    def _sleep_before_retry(self, *, attempt: int, response: requests.Response | None) -> None:
        retry_delay = self._retry_delay_seconds(attempt=attempt, response=response)
        if response is not None and response.status_code == 429:
            # Push the shared (cross-source, cross-process) gate into the cooldown.
            self.throttle.pause_for(retry_delay)
        if retry_delay > 0:
            (self.sleep_fn or sleep)(retry_delay)

    def _retry_delay_seconds(self, *, attempt: int, response: requests.Response | None) -> float:
        retry_after = retry_after_seconds(response.headers.get("Retry-After")) if response is not None else None
        if retry_after is not None:
            return retry_after
        if response is not None and response.status_code == 429:
            return self.rate_limit_sleep_seconds
        return min(60.0, self.retry_backoff_seconds * (2**attempt))


class PncpDirectCollector:
    """Municipal PNCP-direct collector with durable, atomic page/checkpoint state."""

    def __init__(self, config: PncpDirectConfig, *, reporter: Any | None = None,
                 control: Any | None = None, throttle: Any | None = None):
        self.config = config
        self.reporter = reporter
        self.control = control
        self.client = PncpDirectClient(
            timeout=config.request_timeout,
            max_retries=config.request_retries,
            rate_limit_sleep_seconds=config.rate_limit_sleep_seconds,
            request_interval_seconds=config.delay_seconds,
            throttle=throttle,
            sleep_fn=self._sleep,
        )
        self.warehouse = BronzeWarehouse(config.bronze_db_path)
        self.crawl_state = CrawlState(self.warehouse)
        self.ops_store = SqliteOpsStore(config.ops_db_path)
        self.run_id = ""
        self.stats: dict[str, dict[str, int]] = defaultdict(lambda: {"pages": 0, "records": 0, "errors": 0})
        self.errors: list[dict[str, Any]] = []

    def run(self) -> PncpDirectResult:
        self.warehouse.init_schema()
        self.crawl_state.init_schema()
        self.ops_store.init_schema()
        self.run_id = self.ops_store.start_run(
            base_url=self.config.consulta_api_base,
            scope=f"pncp-direct:{self.config.state_uf}:{self.config.municipality_code}:{self.config.start_date}:{self.config.end_date}",
            data_db_path=self.config.db_path,
            bronze_db_path=self.config.bronze_db_path,
        )
        self._log(f"run_id={self.run_id}")
        status = "finished"
        try:
            self._run_phases()
            if self.errors:
                status = "partial"
        except CrawlStopped:
            status = "stopped"
            raise
        except BaseException:
            status = "failed"
            raise
        finally:
            self.ops_store.finish_run(self.run_id, status=status)
        return PncpDirectResult(
            run_id=self.run_id,
            bronze_db_path=self.config.bronze_db_path,
            ops_db_path=self.config.ops_db_path,
            stats={key: dict(value) for key, value in self.stats.items()},
            errors=tuple(self.errors),
        )

    def _run_phases(self) -> None:
        self._log("[1/3] Modalidades (domínio publicado)")
        modalities = self._resolve_modalities()
        self._log(f"  modalidades={len(modalities)}")
        self._log("[2/3] Compras por publicação")
        purchases = self._crawl_purchase_listings(modalities)
        excluded = self.stats["listagem"].get("purchases_excluded", 0)
        self._log(f"  compras válidas={len(purchases)} excluídas={excluded}")
        self._log("[3/3] Itens e resultados")
        self._crawl_purchases(purchases)

    def _resolve_modalities(self) -> list[int]:
        if self.config.modalities is not None:
            self.stats["pncp_direto_modalidades"]["domain_fetched"] = 0
            return list(self.config.modalities)
        records = self._crawl_pages(
            kind="modalidades",
            url=f"{self.config.pncp_api_base.rstrip('/')}/modalidades",
            params={},
            expect="children",
            entity_name=ENTITY_MODALITY,
            single=True,
        )
        codes = record_modality_codes(records)
        if not codes:
            self._record_error("pncp_direto_modalidades", None, "PNCP modality domain returned no codes", None)
        return codes

    def _crawl_purchase_listings(self, modalities: list[int]) -> list[PurchaseIdentity]:
        listing_url = f"{self.config.consulta_api_base.rstrip('/')}/contratacoes/publicacao"
        identities: list[PurchaseIdentity] = []
        seen: set[str] = set()
        for modality in modalities:
            params = {
                "dataInicial": self.config.start_date.replace("-", ""),
                "dataFinal": self.config.end_date.replace("-", ""),
                "codigoModalidadeContratacao": modality,
                "codigoMunicipioIbge": self.config.municipality_code,
                "uf": self.config.state_uf,
            }
            records = self._crawl_pages(
                kind="listagem",
                url=listing_url,
                params=params,
                expect="listing",
                entity_name=ENTITY_PURCHASE,
                modality=modality,
            )
            for row in records:
                identity, problems = self._purchase_record(row, modality)
                if problems:
                    stats = self.stats["listagem"]
                    stats["purchases_excluded"] = stats.get("purchases_excluded", 0) + 1
                    self._record_error(
                        f"pncp_direto_listagem_mod_{sanitize(modality)}", 1,
                        "compra excluída do fanout: " + "; ".join(problems), row,
                    )
                    continue
                if identity.control in seen:
                    continue
                seen.add(identity.control)
                identities.append(identity)
        identities = self._limited(identities, self.config.max_purchases, "compras")
        return identities

    def _purchase_record(self, row: dict[str, Any], modality: int) -> tuple[PurchaseIdentity | None, list[str]]:
        problems: list[str] = []
        control = row.get("numeroControlePNCP")
        if control in (None, ""):
            return None, ["compra sem numeroControlePNCP"]
        problems.extend(control_incoherence(control, row))
        unit_ibge = nested_first(row, ("unidadeOrgao", "codigoIbge"), "unidadeOrgaoCodigoIbge")
        if unit_ibge is not None and str(unit_ibge) != str(self.config.municipality_code):
            problems.append(
                f"município retornado diverge do filtro: {unit_ibge} != {self.config.municipality_code}"
            )
        parts = parse_pncp_control(control)
        if parts is None:
            # Unparseable control keeps its raw-string identity in Bronze, but it
            # cannot prove the parentage needed for the items/results fanout.
            problems.append("controle estrutural não verificável; fanout não iniciado")
            stats = self.stats["listagem"]
            stats["structurally_unverifiable_controls"] = stats.get("structurally_unverifiable_controls", 0) + 1
            return None, problems
        if problems:
            return None, problems
        body_year = nested_first(row, "anoCompra")
        body_sequencial = nested_first(row, "sequencialCompra")
        year = int(body_year) if str(body_year or "").strip().isdigit() else parts["ano"]
        sequencial = int(body_sequencial) if str(body_sequencial or "").strip().isdigit() else parts["sequencial"]
        stats = self.stats["listagem"]
        stats["purchases_valid"] = stats.get("purchases_valid", 0) + 1
        return PurchaseIdentity(control=str(control), cnpj=parts["cnpj"], year=year, sequencial=sequencial), []

    def _crawl_purchases(self, purchases: list[PurchaseIdentity]) -> None:
        total = len(purchases)
        for index, identity in enumerate(purchases, start=1):
            if index % 100 == 0:
                self._log(f"  compra {index}/{total}")
            self._check_stop()
            self._crawl_items(identity)

    def _crawl_items(self, identity: PurchaseIdentity) -> None:
        items = self._crawl_pages(
            kind="itens",
            url=f"{self.config.pncp_api_base.rstrip('/')}{identity.route_base}/itens",
            params={},
            expect="children",
            entity_name=ENTITY_ITEM,
            parent_control=identity.control,
        )
        quantity = self._verify_items_quantity(identity, len(items))
        job_name = f"pncp_direto_itens_{sanitize(identity.control)}"
        self.stats[job_name]["quantity_observed"] = quantity if quantity is not None else -1
        for item in items:
            numero_item = item.get("numeroItem")
            if numero_item in (None, ""):
                self._record_error(job_name, None, "item sem identificador estável (numeroItem)", item)
                self.stats[job_name]["items_without_stable_id"] = \
                    self.stats[job_name].get("items_without_stable_id", 0) + 1
                continue
            flag = item.get("temResultado")
            if flag is False:
                # Publicly observable fact at collection time; not equal to a full
                # harvest of historical results.
                bucket = self.stats[job_name]
                bucket["results_not_published"] = bucket.get("results_not_published", 0) + 1
                continue
            # True, missing/None and unknown values are all harvested.
            self._crawl_results(identity, numero_item)

    def _verify_items_quantity(self, identity: PurchaseIdentity, collected_items: int) -> int | None:
        url = f"{self.config.pncp_api_base.rstrip('/')}{identity.route_base}/itens/quantidade"
        job_name = self._job_name(kind="itens_quantidade", entity_name=ENTITY_ITEM, modality=None,
                                  parent_control=identity.control, parent_item=None)
        self._crawl_pages(
            kind="itens_quantidade",
            url=url,
            params={},
            expect="quantity",
            entity_name=ENTITY_ITEM,
            parent_control=identity.control,
            single=True,
        )
        key = self._job_key(kind="itens_quantidade", url=url, modality=None, parent_control=identity.control,
                            parent_item=None, single=True)
        state = self.crawl_state.open_job(key, job_name, resume=True)
        pages = self.crawl_state.load_pages(key, job_name, state["generation"])
        if not pages:
            self._record_error(job_name, None, "quantidade de itens não verificada na fonte", None)
            return None
        payload = pages[-1][1]
        observed = quantity_from_payload(payload)
        if observed is None:
            self._record_error(job_name, None, f"quantidade de itens ininteligível: {payload!r}", payload)
            return None
        if observed != collected_items:
            self._record_error(
                job_name, None,
                f"divergência de quantidade: fonte={observed} coletado={collected_items}", payload,
            )
        return observed

    def _crawl_results(self, identity: PurchaseIdentity, numero_item: Any) -> None:
        job_name = f"pncp_direto_resultados_item_{sanitize(numero_item)}_{sanitize(identity.control)}"
        records = self._crawl_pages(
            kind="resultados",
            url=(f"{self.config.pncp_api_base.rstrip('/')}{identity.route_base}"
                 f"/itens/{numero_item}/resultados"),
            params={},
            expect="children",
            entity_name=ENTITY_RESULT,
            parent_control=identity.control,
            parent_item=numero_item,
            single=True,
        )
        for row in records:
            body_control = row.get("numeroControlePNCPCompra")
            if body_control not in (None, "") and str(body_control) != identity.control:
                self._record_error(
                    job_name, None,
                    f"resultado contradiz a parentagem do endpoint: {body_control} != {identity.control}", row,
                )
            body_item = row.get("numeroItem")
            if body_item not in (None, "") and str(body_item) != str(numero_item):
                self._record_error(
                    job_name, None,
                    f"resultado de item contraditório: {body_item} != {numero_item}", row,
                )

    def _crawl_pages(self, *, kind: str, url: str, params: dict[str, Any], expect: str,
                     entity_name: str, modality: int | None = None,
                     parent_control: str | None = None, parent_item: Any | None = None,
                     single: bool = False, max_pages: int | None = None) -> list[dict[str, Any]]:
        self._check_stop()
        job_name = self._job_name(kind=kind, entity_name=entity_name, modality=modality,
                                  parent_control=parent_control, parent_item=parent_item)
        key = self._job_key(kind=kind, url=url, modality=modality, parent_control=parent_control,
                            parent_item=parent_item, single=single)
        state = self.crawl_state.open_job(key, job_name, resume=self.config.resume)
        pages = self.crawl_state.load_pages(key, job_name, state["generation"])
        records: list[dict[str, Any]] = list(self.crawl_state.records(pages))
        self.stats[job_name]["pages"] += len(pages)
        self.stats[job_name]["records"] += len(records)
        if state["complete"]:
            self._log(f"  {job_name}: retomado, completo, records={len(records)}")
            return records
        provenance = self._provenance(kind=kind, url=url, modality=modality,
                                      parent_control=parent_control, parent_item=parent_item)
        page = state["next_page"]
        # Repeated-content detection compares page data, not the full envelope:
        # a server that re-serves the same rows on the next page repeats content.
        seen_hashes = {self._repetition_hash(kind, payload) for _, payload, _ in pages}
        limit = max_pages if max_pages is not None else self.config.max_pages_per_job
        while page <= limit:
            self._check_stop()
            request_params = dict(params)
            if not single:
                request_params["pagina"] = page
                if kind in ("listagem", "itens"):
                    request_params.setdefault("tamanhoPagina", self.config.page_size)
            page_data = self._fetch_page(job_name=job_name, url=url, params=request_params, expect=expect)
            if page_data is None:
                break
            payload_hash = stable_hash(page_data.raw)
            repetition_hash = self._repetition_hash(kind, page_data.raw)
            if not single and page > 1 and repetition_hash in seen_hashes:
                self._record_error(job_name, page, "repeated page before pagination completed", None)
                break
            seen_hashes.add(repetition_hash)
            more = self._should_continue(page_data, kind=kind, single=single,
                                         page_size=request_params.get("tamanhoPagina"))
            # Page plus checkpoint advance commit in the same transaction.
            self.crawl_state.commit_page(key=key, generation=state["generation"], job_name=job_name,
                                         entity_name=entity_name, run_id=self.run_id, page=page_data,
                                         complete=not more, auth_used=False, extra_metadata=provenance)
            self.ops_store.save_checkpoint(key, next_page=page + 1, payload_hash=payload_hash)
            records.extend(page_data.records)
            self.stats[job_name]["pages"] += 1
            self.stats[job_name]["records"] += len(page_data.records)
            if not more:
                break
            page += 1
        if page > limit:
            self._record_error(job_name, limit, f"max_pages_per_job reached ({limit})", None)
        self._log(f"  {job_name}: pages={self.stats[job_name]['pages']} records={self.stats[job_name]['records']}")
        return records

    @staticmethod
    def _repetition_hash(kind: str, raw: Any) -> str:
        """Hash of page content without pagination-identity envelope fields."""
        if isinstance(raw, list):
            return stable_hash(raw)
        if isinstance(raw, dict):
            data = raw.get("data")
            if isinstance(data, list):
                return stable_hash(data)
            return stable_hash({
                key: value for key, value in raw.items()
                if key not in ("numeroPagina", "paginasRestantes", "totalPaginas", "totalRegistros")
            })
        return stable_hash(raw)

    def _should_continue(self, page_data: PageData, *, kind: str, single: bool,
                         page_size: int | None = None) -> bool:
        raw = page_data.raw
        if single:
            # Operations without a documented pagination parameter are fetched once.
            return False
        if kind == "listagem" and isinstance(raw, dict):
            if "paginasRestantes" in raw:
                return int(raw.get("paginasRestantes") or 0) > 0
            if "totalPaginas" in raw:
                return page_data.page_number < int(raw.get("totalPaginas") or 0)
        if kind == "itens":
            # Children return arrays with no continuation envelope: a full page
            # (page_size rows) may have a next page; a shorter page is the last.
            return bool(page_data.records) and page_size is not None \
                and len(page_data.records) >= int(page_size)
        return bool(page_data.records)

    def _fetch_page(self, *, job_name: str, url: str, params: dict[str, Any], expect: str) -> PageData | None:
        attempts = 0
        while True:
            self._check_stop()
            try:
                return self.client.fetch(url, params, expect=expect)
            except (CrawlStopped, CrawlDiskReserve):
                raise
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code in (401, 403):
                    # Consultation is public; no token escalation exists here by design.
                    self._record_error(
                        job_name, int(params.get("pagina", 1) or 1),
                        f"HTTP {status_code}: {exc}; nenhuma credencial foi enviada ao PNCP", None,
                    )
                    return None
                if status_code == 429 and attempts < self.config.rate_limit_retries:
                    attempts += 1
                    retry_after = retry_after_seconds(
                        getattr(exc.response, "headers", {}).get("Retry-After") if exc.response is not None else None
                    )
                    sleep_seconds = retry_after if retry_after is not None else self.config.rate_limit_sleep_seconds
                    self._log(f"  {job_name}: HTTP 429; aguardando {sleep_seconds:.0f}s ({attempts}/{self.config.rate_limit_retries})")
                    if sleep_seconds:
                        self.client.throttle.pause_for(sleep_seconds)
                        self._sleep(sleep_seconds)
                    continue
                self._record_error(job_name, int(params.get("pagina", 1) or 1), f"HTTP {status_code}: {exc}", None)
                return None
            except Exception as exc:  # noqa: BLE001
                self._record_error(job_name, int(params.get("pagina", 1) or 1), str(exc), None)
                return None

    def _record_error(self, job_name: str, page_number: int | None, message: str, payload: Any) -> None:
        self.stats[job_name]["errors"] += 1
        payload_json = stable_json(payload) if payload is not None else None
        self.ops_store.record_error(run_id=self.run_id, job_name=job_name, page_number=page_number,
                                    message=message, payload_json=payload_json)
        self.errors.append({"job_name": job_name, "page_number": page_number, "message": message})
        self._log(f"  ERRO {job_name} page={page_number}: {message}")

    def _limited(self, values: list[PurchaseIdentity], max_count: int, label: str) -> list[PurchaseIdentity]:
        if max_count and len(values) > max_count:
            self._record_error("fanout_limit", None,
                               f"fanout truncated: {len(values)} {label} limited to {max_count}", None)
            return values[:max_count]
        return values

    def _check_stop(self) -> None:
        if self.control is not None:
            self.control.check()

    def _sleep(self, seconds: float) -> None:
        if self.control is not None:
            self.control.wait(seconds)
        else:
            sleep(seconds)

    def _log(self, message: str) -> None:
        if self.reporter is not None:
            handler = getattr(self.reporter, "message", None)
            if handler:
                handler(message)
                return
        print(message)

    def _job_name(self, *, kind: str, entity_name: str, modality: int | None,
                  parent_control: str | None, parent_item: Any | None) -> str:
        display_kind = {"itens_quantidade": "quantidade_itens"}.get(kind, kind)
        parts = ["pncp_direto", display_kind]
        if modality is not None:
            parts.append(f"mod_{sanitize(modality)}")
        if parent_item is not None:
            parts.append(f"item_{sanitize(parent_item)}")
        if parent_control:
            parts.append(sanitize(parent_control))
        return "_".join(parts)

    def _job_key(self, *, kind: str, url: str, modality: int | None, parent_control: str | None,
                 parent_item: Any | None, single: bool) -> str:
        # Resume identity carries source, contract version, collection, host/route,
        # municipality, dates, modality, parentage and pagination (plan §3.2).
        return stable_hash({
            "source": SOURCE_NAME,
            "contract": PNCP_CONTRACT_VERSION,
            "collection": self.config.collection_id or "cli",
            "consulta_base": self.config.consulta_api_base,
            "pncp_base": self.config.pncp_api_base,
            "municipality": self.config.municipality_code,
            "uf": self.config.state_uf,
            "start": self.config.start_date,
            "end": self.config.end_date,
            "kind": kind,
            "modality": modality,
            "parent_control": parent_control,
            "parent_item": None if parent_item is None else str(parent_item),
            "single": single,
            "page_size": None if single else self.config.page_size,
            "url": url,
        })

    def _provenance(self, *, kind: str, url: str, modality: int | None,
                    parent_control: str | None, parent_item: Any | None) -> dict[str, Any]:
        path = urlparse(url).path
        return {
            "_pncp_source": SOURCE_NAME,
            "_pncp_contract": PNCP_CONTRACT_VERSION,
            "_pncp_endpoint_kind": kind,
            "_pncp_route": path,
            "_pncp_modality": modality,
            "_pncp_parent_control": parent_control,
            "_pncp_parent_item": None if parent_item is None else str(parent_item),
        }


def record_modality_codes(records: list[dict[str, Any]]) -> list[int]:
    """Read the domain's published `id`, retaining compatibility with older aliases."""
    codes: set[int] = set()
    for row in records:
        code = nested_first(row, "id", "codigo", "codigoModalidade")
        text = str(code).strip()
        if text.isascii() and text.isdigit() and int(text) > 0:
            codes.add(int(text))
    return sorted(codes)
