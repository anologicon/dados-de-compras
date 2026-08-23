from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable


@dataclass(frozen=True)
class EndpointJob:
    name: str
    operation_id: str
    path: str
    entity_name: str
    key_fields: tuple[str, ...]
    base_params: dict[str, Any]
    accept: str = "json"
    supports_page_size: bool = False


@dataclass(frozen=True)
class OperationSpec:
    operation_id: str
    path: str
    entity_name: str
    job_names: tuple[str, ...]
    accepts: tuple[str, ...]


@dataclass(frozen=True)
class MunicipalityPurchaseRequest:
    start_date: str
    end_date: str
    municipality_code: int | None = None
    state_uf: str | None = None
    sources: tuple[str, ...] = ("pncp",)
    pncp_modalidade_code: int | None = None
    pncp_modalidade_codes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        normalized_sources: list[str] = []
        seen_sources: set[str] = set()
        for source in self.sources:
            normalized = source.strip().lower()
            if not normalized or normalized in seen_sources:
                continue
            normalized_sources.append(normalized)
            seen_sources.add(normalized)
        if not normalized_sources:
            raise ValueError("sources must not be empty")
        object.__setattr__(self, "sources", tuple(normalized_sources))
        if self.state_uf is not None:
            object.__setattr__(self, "state_uf", self.state_uf.strip().upper())
        codes = tuple(self.pncp_modalidade_codes)
        if not codes and self.pncp_modalidade_code is not None:
            codes = (self.pncp_modalidade_code,)
        elif codes and self.pncp_modalidade_code is not None and self.pncp_modalidade_code not in codes:
            codes = (self.pncp_modalidade_code, *codes)
        object.__setattr__(self, "pncp_modalidade_codes", codes)
        object.__setattr__(self, "pncp_modalidade_code", codes[0] if codes else None)


MunicipalityPurchaseSourceBuilder = Callable[[MunicipalityPurchaseRequest], tuple[EndpointJob, ...]]


def _boolean_jobs(
    prefix: str,
    operation_id: str,
    path: str,
    entity_name: str,
    key_fields: tuple[str, ...],
    param_name: str,
    *,
    supports_page_size: bool,
) -> tuple[EndpointJob, EndpointJob]:
    return (
        EndpointJob(
            name=f"{prefix}_true",
            operation_id=operation_id,
            path=path,
            entity_name=entity_name,
            key_fields=key_fields,
            base_params={param_name: True},
            supports_page_size=supports_page_size,
        ),
        EndpointJob(
            name=f"{prefix}_false",
            operation_id=operation_id,
            path=path,
            entity_name=entity_name,
            key_fields=key_fields,
            base_params={param_name: False},
            supports_page_size=supports_page_size,
        ),
    )


def _matches_selector(job: EndpointJob, selector: str) -> bool:
    selector = selector.strip().lower()
    if not selector:
        return False
    name = job.name.lower()
    entity = job.entity_name.lower()
    operation_id = job.operation_id.lower()
    return selector in {name, entity, operation_id} or name.startswith(f"{selector}_")


def _with_page_size(job: EndpointJob, page_size: int | None) -> EndpointJob:
    if page_size is None or not job.supports_page_size:
        return job
    return EndpointJob(
        name=job.name,
        operation_id=job.operation_id,
        path=job.path,
        entity_name=job.entity_name,
        key_fields=job.key_fields,
        base_params={**job.base_params, "tamanhoPagina": page_size},
        accept=job.accept,
        supports_page_size=job.supports_page_size,
    )


def _build_pncp_purchase_jobs(request: MunicipalityPurchaseRequest) -> tuple[EndpointJob, ...]:
    if not request.pncp_modalidade_codes:
        raise ValueError("pncp source requires pncp_modalidade_code")
    jobs: list[EndpointJob] = []
    for pncp_modalidade_code in request.pncp_modalidade_codes:
        pncp_params: dict[str, Any] = {
            "dataPublicacaoPncpInicial": request.start_date,
            "dataPublicacaoPncpFinal": request.end_date,
            "codigoModalidade": pncp_modalidade_code,
        }
        if request.state_uf is not None:
            pncp_params["unidadeOrgaoUfSigla"] = request.state_uf
        if request.municipality_code is not None:
            pncp_params["unidadeOrgaoCodigoIbge"] = request.municipality_code
        jobs.append(
            EndpointJob(
                name=f"pncp_14133_{pncp_modalidade_code}",
                operation_id="consultarContratacoes_PNCP_14133",
                path="/modulo-contratacoes/1_consultarContratacoes_PNCP_14133",
                entity_name="pncp_contratacao",
                key_fields=("idCompra", "numeroControlePNCP"),
                base_params=pncp_params,
                supports_page_size=True,
            )
        )
    return tuple(jobs)


MUNICIPALITY_PURCHASE_SOURCE_BUILDERS: dict[str, MunicipalityPurchaseSourceBuilder] = {
    "pncp": _build_pncp_purchase_jobs,
}


def build_municipality_purchase_manifest(
    start_date: str,
    end_date: str,
    *,
    municipality_code: int,
    state_uf: str | None = None,
    sources: tuple[str, ...] = ("pncp",),
    pncp_modalidade_code: int | None = None,
    pncp_modalidade_codes: tuple[int, ...] = (),
) -> tuple[EndpointJob, ...]:
    request = MunicipalityPurchaseRequest(
        start_date=start_date,
        end_date=end_date,
        municipality_code=municipality_code,
        state_uf=state_uf,
        sources=sources,
        pncp_modalidade_code=pncp_modalidade_code,
        pncp_modalidade_codes=pncp_modalidade_codes,
    )
    jobs: list[EndpointJob] = []
    for source in request.sources:
        builder = MUNICIPALITY_PURCHASE_SOURCE_BUILDERS.get(source)
        if builder is None:
            raise ValueError(f"Unknown municipality purchase source: {source}")
        jobs.extend(builder(request))
    return tuple(jobs)


build_city_purchase_manifest = build_municipality_purchase_manifest


def _pncp_requested(endpoints: tuple[str, ...] | None, pncp_modalidade_codes: tuple[int, ...]) -> bool:
    if pncp_modalidade_codes:
        return True
    if not endpoints:
        return False
    return any(
        _matches_selector(
            EndpointJob(
                name="pncp_14133",
                operation_id="consultarContratacoes_PNCP_14133",
                path="/modulo-contratacoes/1_consultarContratacoes_PNCP_14133",
                entity_name="pncp_contratacao",
                key_fields=("idCompra", "numeroControlePNCP"),
                base_params={},
            ),
            endpoint,
        )
        for endpoint in endpoints
    )


def build_historical_manifest(
    start_date: str,
    end_date: str,
    *,
    page_size: int | None = None,
    endpoints: tuple[str, ...] | None = None,
    state_uf: str | None = None,
    municipality_code: int | None = None,
    pncp_modalidade_code: int | None = None,
    pncp_modalidade_codes: tuple[int, ...] = (),
) -> tuple[EndpointJob, ...]:
    jobs: list[EndpointJob] = [
        *_boolean_jobs("uasg", "consultarUasg", "/modulo-uasg/1_consultarUasg", "uasg", ("codigoUasg", "codigo_uasg"), "statusUasg", supports_page_size=False),
        EndpointJob(
            name="licitacao",
            operation_id="consultarLicitacao",
            path="/modulo-legado/1_consultarLicitacao",
            entity_name="licitacao",
            key_fields=("idCompra", "id_compra", "codigoCompra"),
            base_params={
                "data_publicacao_inicial": start_date,
                "data_publicacao_final": end_date,
            },
            supports_page_size=True,
        ),
        *_boolean_jobs("material_group", "consultarGrupoMaterial", "/modulo-material/1_consultarGrupoMaterial", "material_group", ("codigoGrupo", "codigo_grupo"), "statusGrupo", supports_page_size=True),
        *_boolean_jobs("material_class", "consultarClasseMaterial", "/modulo-material/2_consultarClasseMaterial", "material_class", ("codigoClasse", "codigo_classe"), "statusClasse", supports_page_size=True),
        *_boolean_jobs("material_pdm", "consultarPdmMaterial", "/modulo-material/3_consultarPdmMaterial", "material_pdm", ("codigoPdm", "codigo_pdm"), "statusPdm", supports_page_size=True),
        *_boolean_jobs("material_item", "consultarItemMaterial", "/modulo-material/4_consultarItemMaterial", "material_item", ("codigoItem", "codigo_item"), "statusItem", supports_page_size=True),
    ]
    if state_uf is not None:
        jobs = [
            EndpointJob(
                name=job.name,
                operation_id=job.operation_id,
                path=job.path,
                entity_name=job.entity_name,
                key_fields=job.key_fields,
                base_params={**job.base_params, **({"siglaUf": state_uf} if job.operation_id == "consultarUasg" else {})},
                accept=job.accept,
                supports_page_size=job.supports_page_size,
            )
            for job in jobs
        ]
    if not pncp_modalidade_codes and pncp_modalidade_code is not None:
        pncp_modalidade_codes = (pncp_modalidade_code,)
    elif pncp_modalidade_codes and pncp_modalidade_code is not None and pncp_modalidade_code not in pncp_modalidade_codes:
        pncp_modalidade_codes = (pncp_modalidade_code, *pncp_modalidade_codes)
    if _pncp_requested(endpoints, pncp_modalidade_codes):
        if not pncp_modalidade_codes:
            raise ValueError("consultarContratacoes_PNCP_14133 requires pncp_modalidade_code")
        jobs.extend(
            _build_pncp_purchase_jobs(
                MunicipalityPurchaseRequest(
                    start_date=start_date,
                    end_date=end_date,
                    municipality_code=municipality_code,
                    state_uf=state_uf,
                    pncp_modalidade_codes=pncp_modalidade_codes,
                )
            )
        )
    if endpoints:
        selected = [job for job in jobs if any(_matches_selector(job, endpoint) for endpoint in endpoints)]
        if not selected:
            raise ValueError(f"No endpoints matched: {', '.join(endpoints)}")
        jobs = selected
    jobs = [_with_page_size(job, page_size) for job in jobs]
    return tuple(jobs)


def build_operation_catalog(jobs: tuple[EndpointJob, ...]) -> tuple[OperationSpec, ...]:
    catalog: list[OperationSpec] = []
    seen: set[str] = set()
    for job in jobs:
        if job.operation_id in seen:
            continue
        grouped = tuple(item for item in jobs if item.operation_id == job.operation_id)
        catalog.append(
            OperationSpec(
                operation_id=job.operation_id,
                path=job.path,
                entity_name=job.entity_name,
                job_names=tuple(item.name for item in grouped),
                accepts=tuple(dict.fromkeys(item.accept for item in grouped)),
            )
        )
        seen.add(job.operation_id)
    return tuple(catalog)


def default_date_window() -> tuple[str, str]:
    yesterday = date.today() - timedelta(days=1)
    day = yesterday.isoformat()
    return day, day
