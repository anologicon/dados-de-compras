from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


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


def _pncp_requested(endpoints: tuple[str, ...] | None, pncp_modalidade_code: int | None) -> bool:
    if pncp_modalidade_code is not None:
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
    if _pncp_requested(endpoints, pncp_modalidade_code):
        if pncp_modalidade_code is None:
            raise ValueError("consultarContratacoes_PNCP_14133 requires pncp_modalidade_code")
        pncp_params: dict[str, Any] = {
            "dataPublicacaoPncpInicial": start_date,
            "dataPublicacaoPncpFinal": end_date,
            "codigoModalidade": pncp_modalidade_code,
        }
        if state_uf is not None:
            pncp_params["unidadeOrgaoUfSigla"] = state_uf
        if municipality_code is not None:
            pncp_params["unidadeOrgaoCodigoIbge"] = municipality_code
        jobs.append(
            EndpointJob(
                name="pncp_14133",
                operation_id="consultarContratacoes_PNCP_14133",
                path="/modulo-contratacoes/1_consultarContratacoes_PNCP_14133",
                entity_name="pncp_contratacao",
                key_fields=("idCompra", "numeroControlePNCP"),
                base_params=pncp_params,
                supports_page_size=True,
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
