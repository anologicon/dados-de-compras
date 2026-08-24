from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from time import sleep
from typing import Any, Iterable
import json
import re

import requests

from .client import ComprasClient, PageData, retry_after_seconds, validate_base_url
from .normalize import extract_records, stable_hash, stable_json
from .storage import DEFAULT_DB_PREFIX, BronzeWarehouse, SqliteOpsStore, derive_bronze_db_path, derive_ops_db_path

DEFAULT_BASE_URL = "https://dadosabertos.compras.gov.br"
DEFAULT_PNCP_MODALIDADES = tuple(range(1, 14))


@dataclass(frozen=True)
class FullCityConfig:
    """Configuration for a best-effort full public API crawl for one municipality.

    The Compras.gov.br API is not a single flat dump: many endpoints require IDs
    obtained from other endpoints. This crawler starts from municipality/date
    roots, derives IDs, then calls the related public endpoints. Protected/admin
    endpoints are not called by default. When a token is configured, it is only
    retried after a public request returns 401/403.
    """

    db_path: Path = DEFAULT_DB_PREFIX
    ops_db_path: Path | None = None
    bronze_db_path: Path | None = None
    base_url: str = DEFAULT_BASE_URL
    token: str | None = None
    start_date: str = "2026-01-01"
    end_date: str = "2026-12-31"
    state_uf: str = "SC"
    municipality_code: int = 4205407
    page_size: int | None = 100
    max_pages_per_job: int = 500
    max_purchases: int = 0
    max_units: int = 0
    max_suppliers: int = 500
    max_price_items: int = 500
    delay_seconds: float = 1.0
    rate_limit_sleep_seconds: float = 60.0
    rate_limit_retries: int = 3
    request_timeout: float = 45.0
    request_retries: int = 5
    resume: bool = True
    include_reference_catalogs: bool = True
    include_price_research: bool = True
    include_csv_variants: bool = False
    include_protected_admin: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "db_path", Path(self.db_path))
        object.__setattr__(self, "bronze_db_path", Path(self.bronze_db_path) if self.bronze_db_path else derive_bronze_db_path(self.db_path))
        object.__setattr__(self, "ops_db_path", Path(self.ops_db_path) if self.ops_db_path else derive_ops_db_path(self.db_path))
        object.__setattr__(self, "state_uf", self.state_uf.strip().upper())
        validate_base_url(self.base_url, token=self.token)
        if len(self.state_uf) != 2:
            raise ValueError("state_uf must be a 2-letter UF abbreviation")
        if self.municipality_code <= 0:
            raise ValueError("municipality_code must be positive")
        if self.page_size is not None and self.page_size <= 0:
            raise ValueError("page_size must be positive")
        for field_name in (
            "max_pages_per_job",
            "max_purchases",
            "max_units",
            "max_suppliers",
            "max_price_items",
            "rate_limit_retries",
            "request_retries",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be greater than or equal to zero")
        if self.delay_seconds < 0 or self.rate_limit_sleep_seconds < 0 or self.request_timeout <= 0:
            raise ValueError("timeouts and delays must be non-negative, and request_timeout must be positive")


@dataclass(frozen=True)
class FullCityResult:
    run_id: str
    bronze_db_path: Path
    ops_db_path: Path
    stats: dict[str, dict[str, int]]
    errors: tuple[dict[str, Any], ...]
    skipped_operations: tuple[str, ...] = field(default_factory=tuple)


class FullCityCrawler:
    def __init__(self, config: FullCityConfig, *, reporter: Any | None = None):
        self.config = config
        self.reporter = reporter
        self.client = ComprasClient(
            config.base_url,
            token=config.token,
            timeout=config.request_timeout,
            max_retries=config.request_retries,
            rate_limit_sleep_seconds=config.rate_limit_sleep_seconds,
        )
        self.warehouse = BronzeWarehouse(config.bronze_db_path)
        self.ops_store = SqliteOpsStore(config.ops_db_path)
        self.run_id = ""
        self.stats: dict[str, dict[str, int]] = defaultdict(lambda: {"pages": 0, "records": 0, "errors": 0, "auth_retries": 0})
        self.errors: list[dict[str, Any]] = []
        self.skipped_operations: list[str] = []

    def run(self) -> FullCityResult:
        self.warehouse.init_schema()
        self.ops_store.init_schema()
        self.run_id = self.ops_store.start_run(
            base_url=self.config.base_url,
            scope=f"full-city:{self.config.state_uf}:{self.config.municipality_code}:{self.config.start_date}:{self.config.end_date}",
            data_db_path=self.config.db_path,
            bronze_db_path=self.config.bronze_db_path,
        )
        self._log(f"run_id={self.run_id}")
        status = "finished"
        try:
            self._run_phases()
        except Exception:
            status = "failed"
            raise
        finally:
            self.ops_store.finish_run(self.run_id, status=status)
        return FullCityResult(
            run_id=self.run_id,
            bronze_db_path=self.config.bronze_db_path,
            ops_db_path=self.config.ops_db_path,
            stats={key: dict(value) for key, value in self.stats.items()},
            errors=tuple(self.errors),
            skipped_operations=tuple(self.skipped_operations),
        )

    def _run_phases(self) -> None:
        self._log("[1/9] PNCP contratações por modalidade")
        pncp_compras = self._crawl_pncp_contratacoes()
        purchase_ids = self._limited(unique_sorted(first_present(row, "idCompra") for row in pncp_compras), self.config.max_purchases)
        pncp_units = unique_sorted(first_present(row, "unidadeOrgaoCodigoUnidade") for row in pncp_compras)
        pncp_orgao_codes = unique_sorted(first_present(row, "codigoOrgao") for row in pncp_compras)
        pncp_cnpjs = unique_sorted(first_present(row, "orgaoEntidadeCnpj") for row in pncp_compras)
        self._log(f"  compras={len(pncp_compras)} idCompra={len(purchase_ids)} unidades={len(pncp_units)}")

        self._log("[2/9] UASG e órgãos relacionados")
        uasg_floripa = self._crawl_uasg_floripa()
        uasg_units = unique_sorted(first_present(row, "codigoUasg") for row in uasg_floripa)
        units = self._limited(sorted(set(pncp_units) | set(uasg_units)), self.config.max_units)
        orgao_codes = sorted(set(pncp_orgao_codes) | set(unique_sorted(first_present(row, "codigoOrgao") for row in uasg_floripa)))
        orgao_cnpjs = sorted(set(pncp_cnpjs) | set(unique_sorted(first_present(row, "cnpjCpfOrgao") for row in uasg_floripa)))
        self._crawl_orgaos(orgao_codes)
        self._log(f"  uasgs_floripa={len(uasg_floripa)} unidades={len(units)} orgaos={len(orgao_codes)}")

        self._log("[3/9] PNCP por idCompra, itens e resultados")
        pncp_details, pncp_items, pncp_results = self._crawl_pncp_ids(purchase_ids)
        self._log(f"  detalhes={len(pncp_details)} itens={len(pncp_items)} resultados={len(pncp_results)}")

        self._log("[4/9] Legado por UASG")
        legacy_records = self._crawl_legado(units)
        legacy_purchase_ids = unique_sorted(first_present(row, "idCompra", "id_compra", "idCompraLicitacao") for row in legacy_records)
        self._crawl_legado_ids(legacy_purchase_ids)
        self._log(f"  legado={len(legacy_records)} ids={len(legacy_purchase_ids)}")

        self._log("[5/9] ARP e itens")
        arp_records = self._crawl_arp(units)
        self._crawl_arp_ids(arp_records)
        self._log(f"  arp={len(arp_records)}")

        self._log("[6/9] Contratos e itens")
        contrato_records = self._crawl_contratos(units, orgao_codes, uasg_floripa, pncp_compras)
        self._crawl_contrato_ids(contrato_records)
        self._log(f"  contratos={len(contrato_records)}")

        self._log("[7/9] PGC e OCDS")
        pgc_records = self._crawl_pgc(orgao_codes)
        self._crawl_pgc_catalogo(pgc_records)
        self._crawl_ocds(orgao_cnpjs)
        self._log(f"  pgc={len(pgc_records)} buyer_ids={len(orgao_cnpjs)}")

        supplier_ids = unique_sorted(
            first_present(row, "niFornecedor", "nu_cpf_cnpj_fornecedor", "fornecedor_vencedor")
            for row in [*pncp_results, *legacy_records, *contrato_records]
        )
        self._log("[8/9] Fornecedores derivados")
        self._crawl_fornecedores(self._limited(supplier_ids, self.config.max_suppliers))

        item_rows = [*pncp_items, *legacy_records, *arp_records, *contrato_records]
        if self.config.include_reference_catalogs:
            self._log("[9/9] Catálogos derivados")
            self._crawl_catalogos_derivados(item_rows)
        else:
            self.skipped_operations.append("catalogos_derivados")
        if self.config.include_price_research:
            self._log("[extra] Pesquisa de preço derivada")
            self._crawl_pesquisa_preco(item_rows)
        else:
            self.skipped_operations.append("pesquisa_preco")
        if not self.config.include_protected_admin:
            self.skipped_operations.extend(["usuarios", "alice"])

    def _crawl_pncp_contratacoes(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for modalidade in DEFAULT_PNCP_MODALIDADES:
            records.extend(
                self.fetch_paginated(
                    job_name=f"pncp_contratacoes_modalidade_{modalidade}",
                    entity_name="pncp_contratacao",
                    path="/modulo-contratacoes/1_consultarContratacoes_PNCP_14133",
                    params={
                        "dataPublicacaoPncpInicial": self.config.start_date,
                        "dataPublicacaoPncpFinal": self.config.end_date,
                        "codigoModalidade": modalidade,
                        "unidadeOrgaoCodigoIbge": self.config.municipality_code,
                        "unidadeOrgaoUfSigla": self.config.state_uf,
                    },
                )
            )
        return records

    def _crawl_uasg_floripa(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for active in (True, False):
            records.extend(
                self.fetch_paginated(
                    job_name=f"uasg_{self.config.state_uf.lower()}_status_{str(active).lower()}",
                    entity_name="uasg",
                    path="/modulo-uasg/1_consultarUasg",
                    params={"statusUasg": active, "siglaUf": self.config.state_uf},
                )
            )
        return [row for row in records if str(row.get("codigoMunicipioIbge")) == str(self.config.municipality_code)]

    def _crawl_orgaos(self, orgao_codes: list[str]) -> None:
        for codigo_orgao in orgao_codes:
            for active in (True, False):
                self.fetch_paginated(
                    job_name=f"orgao_{sanitize(codigo_orgao)}_status_{str(active).lower()}",
                    entity_name="orgao",
                    path="/modulo-uasg/2_consultarOrgao",
                    params={"codigoOrgao": codigo_orgao, "statusOrgao": active},
                    max_pages=10,
                )

    def _crawl_pncp_ids(self, purchase_ids: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        details: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        total = len(purchase_ids)
        for index, purchase_id in enumerate(purchase_ids, start=1):
            if index % 100 == 0:
                self._log(f"  idCompra {index}/{total}")
            details.extend(
                self.fetch_once(
                    job_name=f"pncp_contratacao_id_{sanitize(purchase_id)}",
                    entity_name="pncp_contratacao_id",
                    path="/modulo-contratacoes/1.1_consultarContratacoes_PNCP_14133_Id",
                    params={"tipo": "idCompra", "codigo": purchase_id},
                )
            )
            items.extend(
                self.fetch_once(
                    job_name=f"pncp_itens_id_{sanitize(purchase_id)}",
                    entity_name="pncp_item_contratacao",
                    path="/modulo-contratacoes/2.1_consultarItensContratacoes_PNCP_14133_Id",
                    params={"tipo": "idCompra", "codigo": purchase_id},
                )
            )
            results.extend(
                self.fetch_once(
                    job_name=f"pncp_resultados_id_{sanitize(purchase_id)}",
                    entity_name="pncp_resultado_item",
                    path="/modulo-contratacoes/3.1_consultarResultadoItensContratacoes_PNCP_14133_Id",
                    params={"tipo": "idCompra", "codigo": purchase_id},
                )
            )
        return details, items, results

    def _crawl_legado(self, units: list[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        year = int(self.config.start_date[:4])
        for unit in units:
            unit_job = sanitize(unit)
            records.extend(self.fetch_paginated(job_name=f"legado_licitacao_uasg_{unit_job}", entity_name="licitacao", path="/modulo-legado/1_consultarLicitacao", params={"data_publicacao_inicial": self.config.start_date, "data_publicacao_final": self.config.end_date, "uasg": unit}))
            records.extend(self.fetch_paginated(job_name=f"legado_pregoes_uasg_{unit_job}", entity_name="pregao", path="/modulo-legado/3_consultarPregoes", params={"dt_data_edital_inicial": self.config.start_date, "dt_data_edital_final": self.config.end_date, "co_uasg": unit}))
            records.extend(self.fetch_paginated(job_name=f"legado_itens_pregoes_uasg_{unit_job}", entity_name="pregao_item", path="/modulo-legado/4_consultarItensPregoes", params={"dt_hom_inicial": self.config.start_date, "dt_hom_final": self.config.end_date, "co_uasg": unit}))
            records.extend(self.fetch_paginated(job_name=f"legado_compras_sem_licitacao_uasg_{unit_job}", entity_name="compra_sem_licitacao", path="/modulo-legado/5_consultarComprasSemLicitacao", params={"dt_ano_aviso": year, "co_uasg": unit}))
            records.extend(self.fetch_paginated(job_name=f"legado_itens_sem_licitacao_uasg_{unit_job}", entity_name="compra_sem_licitacao_item", path="/modulo-legado/6_consultarCompraItensSemLicitacao", params={"dt_ano_aviso_licitacao": year, "co_uasg": unit}))
            records.extend(self.fetch_paginated(job_name=f"legado_rdc_uasg_{unit_job}", entity_name="rdc", path="/modulo-legado/7_consultarRdc", params={"data_publicacao_min": self.config.start_date, "data_publicacao_max": self.config.end_date, "uasg": unit, "uf_uasg": self.config.state_uf}))
        return records

    def _crawl_legado_ids(self, purchase_ids: list[str]) -> None:
        for purchase_id in purchase_ids:
            pid = sanitize(purchase_id)
            self.fetch_once(job_name=f"legado_licitacao_id_{pid}", entity_name="licitacao_id", path="/modulo-legado/1.1_consultarLicitacao_Id", params={"id_compra": purchase_id})
            self.fetch_once(job_name=f"legado_item_licitacao_id_{pid}", entity_name="licitacao_item_id", path="/modulo-legado/2.1_consultarItemLicitacao_Id", params={"id_compra": purchase_id})
            self.fetch_once(job_name=f"legado_pregoes_id_{pid}", entity_name="pregao_id", path="/modulo-legado/3.1_consultarPregoes_Id", params={"id_compra": purchase_id})
            self.fetch_once(job_name=f"legado_itens_pregoes_id_{pid}", entity_name="pregao_item_id", path="/modulo-legado/4.1_consultarItensPregoes_Id", params={"id_compra": purchase_id})
            self.fetch_once(job_name=f"legado_compra_sem_licitacao_id_{pid}", entity_name="compra_sem_licitacao_id", path="/modulo-legado/5.1_consultarCompraSemLicitacao_Id", params={"idCompra": purchase_id})
            self.fetch_once(job_name=f"legado_itens_sem_licitacao_id_{pid}", entity_name="compra_sem_licitacao_item_id", path="/modulo-legado/6.1_consultarItensComprasSemLicitacao_Id", params={"id_compra": purchase_id})

    def _crawl_arp(self, units: list[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for unit in units:
            unit_job = sanitize(unit)
            records.extend(self.fetch_paginated(job_name=f"arp_inicio_unidade_{unit_job}", entity_name="arp", path="/modulo-arp/1_consultarARP", params={"codigoUnidadeGerenciadora": unit, "dataVigenciaInicialMin": self.config.start_date, "dataVigenciaInicialMax": self.config.end_date}))
            records.extend(self.fetch_paginated(job_name=f"arp_fim_unidade_{unit_job}", entity_name="arp", path="/modulo-arp/1.2_consultarARP_FimVigencia", params={"codigoUnidadeGerenciadora": unit, "dataVigenciaFinalMin": self.config.start_date, "dataVigenciaFinalMax": self.config.end_date}))
            records.extend(self.fetch_paginated(job_name=f"arp_item_unidade_{unit_job}", entity_name="arp_item", path="/modulo-arp/2_consultarARPItem", params={"codigoUnidadeGerenciadora": unit, "dataVigenciaInicialMin": self.config.start_date, "dataVigenciaInicialMax": self.config.end_date}))
        return records

    def _crawl_arp_ids(self, arp_records: list[dict[str, Any]]) -> None:
        for ata in unique_sorted(first_present(row, "numeroControlePncpAta", "numeroControlePNCPAta") for row in arp_records):
            key = sanitize(ata)
            self.fetch_once(job_name=f"arp_id_{key}", entity_name="arp_id", path="/modulo-arp/1.1_consultarARP_Id", params={"numeroControlePncpAta": ata})
            self.fetch_once(job_name=f"arp_item_id_{key}", entity_name="arp_item_id", path="/modulo-arp/2.1_consultarARPItem_Id", params={"numeroControlePncpAta": ata})

    def _crawl_contratos(self, units: list[str], orgao_codes: list[str], uasg_rows: list[dict[str, Any]], pncp_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        orgao_by_unit: dict[str, set[str]] = defaultdict(set)
        for row in [*uasg_rows, *pncp_rows]:
            unit = first_present(row, "codigoUasg", "unidadeOrgaoCodigoUnidade")
            orgao = first_present(row, "codigoOrgao")
            if unit and orgao:
                orgao_by_unit[str(unit)].add(str(orgao))
        if not orgao_by_unit:
            orgao_by_unit = {"": set(orgao_codes)}
        records: list[dict[str, Any]] = []
        for unit in units:
            for orgao in sorted(orgao_by_unit.get(str(unit), ())):
                base = {"codigoOrgao": orgao, "codigoUnidadeGestora": unit}
                suffix = f"orgao_{sanitize(orgao)}_unidade_{sanitize(unit)}"
                records.extend(self.fetch_paginated(job_name=f"contratos_inicio_{suffix}", entity_name="contrato", path="/modulo-contratos/1_consultarContratos", params={**base, "dataVigenciaInicialMin": self.config.start_date, "dataVigenciaInicialMax": self.config.end_date}))
                records.extend(self.fetch_paginated(job_name=f"contratos_fim_{suffix}", entity_name="contrato", path="/modulo-contratos/1.2_consultarContratos_FimVigencia", params={**base, "dataVigenciaFinalMin": self.config.start_date, "dataVigenciaFinalMax": self.config.end_date}))
                records.extend(self.fetch_paginated(job_name=f"contratos_itens_{suffix}", entity_name="contrato_item", path="/modulo-contratos/2_consultarContratosItem", params={**base, "dataVigenciaInicialMin": self.config.start_date, "dataVigenciaInicialMax": self.config.end_date}))
        return records

    def _crawl_contrato_ids(self, contrato_records: list[dict[str, Any]]) -> None:
        for row in contrato_records:
            codigo = first_present(row, "numeroControlePNCPContrato", "numeroControlePncpContrato", "idContrato", "codigoContrato")
            if not codigo:
                continue
            for tipo in ("numeroControlePNCPContrato", "idContrato"):
                key = f"{sanitize(tipo)}_{sanitize(codigo)}"
                self.fetch_once(job_name=f"contratos_id_{key}", entity_name="contrato_id", path="/modulo-contratos/1.1_consultarContratos_Id", params={"tipo": tipo, "codigo": codigo})
                self.fetch_once(job_name=f"contratos_item_id_{key}", entity_name="contrato_item_id", path="/modulo-contratos/2.1_consultarContratosItem_Id", params={"tipo": tipo, "codigo": codigo})

    def _crawl_pgc(self, orgao_codes: list[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        year = int(self.config.start_date[:4])
        for orgao in orgao_codes:
            records.extend(self.fetch_paginated(job_name=f"pgc_detalhe_orgao_{sanitize(orgao)}_{year}", entity_name="pgc_detalhe", path="/modulo-pgc/1_consultarPgcDetalhe", params={"orgao": orgao, "anoPcaProjetoCompra": year}))
            records.extend(self.fetch_paginated(job_name=f"pgc_agregacao_orgao_{sanitize(orgao)}_{year}", entity_name="pgc_agregacao", path="/modulo-pgc/3_consultarPgcAgregacao", params={"orgao": orgao, "ano": year}))
        return records

    def _crawl_pgc_catalogo(self, pgc_records: list[dict[str, Any]]) -> None:
        year = int(self.config.start_date[:4])
        pairs = set()
        for row in pgc_records:
            tipo = first_present(row, "tipoItem", "tipo", "materialOuServico")
            codigo = first_present(row, "codigoItem", "codigoItemCatalogo", "codigoServico", "codigoMaterial")
            if tipo and codigo:
                pairs.add((str(tipo), str(codigo)))
        for tipo, codigo in sorted(pairs):
            key = f"{sanitize(tipo)}_{sanitize(codigo)}"
            self.fetch_paginated(job_name=f"pgc_catalogo_{key}_{year}", entity_name="pgc_catalogo", path="/modulo-pgc/2_consultarPgcDetalheCatalogo", params={"anoPcaProjetoCompra": year, "tipo": tipo, "codigo": codigo}, max_pages=20)

    def _crawl_ocds(self, buyer_ids: list[str]) -> None:
        for buyer_id in buyer_ids:
            self.fetch_once(job_name=f"ocds_releases_buyer_{sanitize(buyer_id)}", entity_name="ocds_release", path="/modulo-ocds/1_releases", params={"buyerID": buyer_id, "releaseStartDate": self.config.start_date, "releaseEndDate": self.config.end_date, "page": 1, "offSet": self.config.page_size or 100})

    def _crawl_fornecedores(self, supplier_ids: list[str]) -> None:
        for supplier in supplier_ids:
            digits = re.sub(r"\D", "", str(supplier))
            if not digits:
                continue
            key = "cnpj" if len(digits) == 14 else "cpf"
            for active in (True, False):
                self.fetch_paginated(job_name=f"fornecedor_{key}_{sanitize(digits)}_ativo_{str(active).lower()}", entity_name="fornecedor", path="/modulo-fornecedor/1_consultarFornecedor", params={key: digits, "ativo": active}, max_pages=10)

    def _crawl_catalogos_derivados(self, item_rows: list[dict[str, Any]]) -> None:
        material_codes: set[str] = set()
        service_codes: set[str] = set()
        pdm_codes: set[str] = set()
        group_codes: set[str] = set()
        class_codes: set[str] = set()
        for row in item_rows:
            item_type = str(first_present(row, "materialOuServico", "tipoItem", "tipo") or "").upper()
            code = first_present(row, "codItemCatalogo", "codigoItemCatalogo", "codigoItem", "codigo_item_material", "codigo_item_servico")
            if code:
                if item_type.startswith("S"):
                    service_codes.add(str(code))
                else:
                    material_codes.add(str(code))
            if first_present(row, "codigoPdm"):
                pdm_codes.add(str(first_present(row, "codigoPdm")))
            if first_present(row, "codigoGrupo"):
                group_codes.add(str(first_present(row, "codigoGrupo")))
            if first_present(row, "codigoClasse"):
                class_codes.add(str(first_present(row, "codigoClasse")))
        for code in sorted(material_codes):
            self.fetch_paginated(job_name=f"catalogo_material_item_{sanitize(code)}", entity_name="material_item", path="/modulo-material/4_consultarItemMaterial", params={"codigoItem": code}, max_pages=10)
            self.fetch_paginated(job_name=f"catalogo_material_caracteristicas_{sanitize(code)}", entity_name="material_characteristics", path="/modulo-material/7_consultarMaterialCaracteristicas", params={"codigoItem": code}, max_pages=10)
        for code in sorted(pdm_codes):
            self.fetch_paginated(job_name=f"catalogo_material_pdm_{sanitize(code)}", entity_name="material_pdm", path="/modulo-material/3_consultarPdmMaterial", params={"codigoPdm": code}, max_pages=10)
            self.fetch_paginated(job_name=f"catalogo_material_unidade_fornecimento_{sanitize(code)}", entity_name="material_supply_unit", path="/modulo-material/6_consultarMaterialUnidadeFornecimento", params={"codigoPdm": code}, max_pages=10)
            self.fetch_paginated(job_name=f"catalogo_material_natureza_despesa_{sanitize(code)}", entity_name="material_expense_nature", path="/modulo-material/5_consultarMaterialNaturezaDespesa", params={"codigoPdm": code}, max_pages=10)
        for code in sorted(group_codes):
            self.fetch_paginated(job_name=f"catalogo_material_grupo_{sanitize(code)}", entity_name="material_group", path="/modulo-material/1_consultarGrupoMaterial", params={"codigoGrupo": code}, max_pages=10)
        for code in sorted(class_codes):
            self.fetch_paginated(job_name=f"catalogo_material_classe_{sanitize(code)}", entity_name="material_class", path="/modulo-material/2_consultarClasseMaterial", params={"codigoClasse": code}, max_pages=10)
        for code in sorted(service_codes):
            self.fetch_paginated(job_name=f"catalogo_servico_item_{sanitize(code)}", entity_name="service_item", path="/modulo-servico/6_consultarItemServico", params={"codigoServico": code}, max_pages=10)
            self.fetch_paginated(job_name=f"catalogo_servico_unidade_{sanitize(code)}", entity_name="service_unit", path="/modulo-servico/7_consultarUndMedidaServico", params={"codigoServico": code}, max_pages=10)
            self.fetch_paginated(job_name=f"catalogo_servico_natureza_despesa_{sanitize(code)}", entity_name="service_expense_nature", path="/modulo-servico/8_consultarNaturezaDespesaServico", params={"codigoServico": code}, max_pages=10)
        self.fetch_paginated(job_name="catalogo_servico_secao", entity_name="service_section", path="/modulo-servico/1_consultarSecaoServico", params={}, max_pages=50)
        self.fetch_paginated(job_name="catalogo_servico_divisao", entity_name="service_division", path="/modulo-servico/2_consultarDivisaoServico", params={}, max_pages=50)
        self.fetch_paginated(job_name="catalogo_servico_grupo", entity_name="service_group", path="/modulo-servico/3_consultarGrupoServico", params={}, max_pages=50)
        self.fetch_paginated(job_name="catalogo_servico_classe", entity_name="service_class", path="/modulo-servico/4_consultarClasseServico", params={}, max_pages=50)
        self.fetch_paginated(job_name="catalogo_servico_subclasse", entity_name="service_subclass", path="/modulo-servico/5_consultarSubClasseServico", params={}, max_pages=50)

    def _crawl_pesquisa_preco(self, item_rows: list[dict[str, Any]]) -> None:
        material_codes: set[str] = set()
        service_codes: set[str] = set()
        for row in item_rows:
            item_type = str(first_present(row, "materialOuServico", "tipoItem", "tipo") or "").upper()
            code = first_present(row, "codItemCatalogo", "codigoItemCatalogo", "codigoItem", "codigo_item_material", "codigo_item_servico")
            if not code:
                continue
            if item_type.startswith("S"):
                service_codes.add(str(code))
            else:
                material_codes.add(str(code))
        material_codes_list = self._limited(sorted(material_codes), self.config.max_price_items)
        service_codes_list = self._limited(sorted(service_codes), self.config.max_price_items)
        for code in material_codes_list:
            self.fetch_paginated(job_name=f"pesquisa_preco_material_detalhe_{sanitize(code)}", entity_name="price_material_detail", path="/modulo-pesquisa-preco/2_consultarMaterialDetalhe", params={"codigoItemCatalogo": code, "dataCompraInicio": self.config.start_date, "dataCompraFim": self.config.end_date}, max_pages=20)
        for code in service_codes_list:
            self.fetch_paginated(job_name=f"pesquisa_preco_servico_{sanitize(code)}", entity_name="price_service", path="/modulo-pesquisa-preco/3_consultarServico", params={"codigoItemCatalogo": code, "estado": self.config.state_uf, "codigoMunicipio": self.config.municipality_code, "dataCompraInicio": self.config.start_date, "dataCompraFim": self.config.end_date}, max_pages=20)
            self.fetch_paginated(job_name=f"pesquisa_preco_servico_detalhe_{sanitize(code)}", entity_name="price_service_detail", path="/modulo-pesquisa-preco/4_consultarServicoDetalhe", params={"codigoItemCatalogo": code, "dataCompraInicio": self.config.start_date, "dataCompraFim": self.config.end_date}, max_pages=20)

    def fetch_paginated(self, *, job_name: str, entity_name: str, path: str, params: dict[str, Any], max_pages: int | None = None) -> list[dict[str, Any]]:
        if self.config.resume and self._job_has_pages(job_name):
            records = self._load_job_records(job_name)
            self._log(f"  {job_name}: resume skip records={len(records)}")
            return records
        records: list[dict[str, Any]] = []
        page = 1
        seen_hashes: set[str] = set()
        limit = max_pages if max_pages is not None else self.config.max_pages_per_job
        while page <= limit:
            request_params = dict(params)
            if self.config.page_size is not None:
                request_params.setdefault("tamanhoPagina", self.config.page_size)
            request_params["pagina"] = page
            page_data, auth_used = self._fetch_page(job_name, path, request_params)
            if page_data is None:
                break
            payload_hash = stable_hash(page_data.raw)
            if page > 1 and payload_hash in seen_hashes:
                break
            seen_hashes.add(payload_hash)
            self._persist_page(job_name, entity_name, page_data, auth_used=auth_used)
            self.ops_store.save_checkpoint(job_name, next_page=page + 1, payload_hash=payload_hash)
            records.extend(page_data.records)
            self.stats[job_name]["pages"] += 1
            self.stats[job_name]["records"] += len(page_data.records)
            if not self._should_continue(page_data):
                break
            page += 1
        if page > limit:
            self._record_error(job_name, limit, f"max_pages_per_job reached ({limit})", None)
        self._log(f"  {job_name}: pages={self.stats[job_name]['pages']} records={self.stats[job_name]['records']}")
        return records

    def fetch_once(self, *, job_name: str, entity_name: str, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if self.config.resume and self._job_has_pages(job_name):
            return self._load_job_records(job_name)
        page_data, auth_used = self._fetch_page(job_name, path, dict(params))
        if page_data is None:
            return []
        self._persist_page(job_name, entity_name, page_data, auth_used=auth_used)
        self.ops_store.save_checkpoint(job_name, next_page=2, payload_hash=stable_hash(page_data.raw))
        self.stats[job_name]["pages"] += 1
        self.stats[job_name]["records"] += len(page_data.records)
        return page_data.records

    def _fetch_page(self, job_name: str, path: str, params: dict[str, Any]) -> tuple[PageData | None, bool]:
        attempts = 0
        while True:
            if self.config.delay_seconds:
                sleep(self.config.delay_seconds)
            try:
                return self.client.fetch_page(path, params, use_auth=False), False
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code in (401, 403) and self.config.token:
                    self.stats[job_name]["auth_retries"] += 1
                    if self.config.delay_seconds:
                        sleep(self.config.delay_seconds)
                    try:
                        return self.client.fetch_page(path, params, use_auth=True), True
                    except Exception as auth_exc:  # noqa: BLE001
                        self._record_error(job_name, int(params.get("pagina", 1) or 1), f"auth retry failed: {auth_exc}", None)
                        return None, True
                if status_code == 429 and attempts < self.config.rate_limit_retries:
                    attempts += 1
                    retry_after = retry_after_seconds(getattr(exc.response, "headers", {}).get("Retry-After") if exc.response is not None else None)
                    sleep_seconds = retry_after if retry_after is not None else self.config.rate_limit_sleep_seconds
                    self._log(f"  {job_name}: HTTP 429; aguardando {sleep_seconds:.0f}s ({attempts}/{self.config.rate_limit_retries})")
                    if sleep_seconds:
                        sleep(sleep_seconds)
                    continue
                self._record_error(job_name, int(params.get("pagina", 1) or 1), f"HTTP {status_code}: {exc}", None)
                return None, False
            except Exception as exc:  # noqa: BLE001
                self._record_error(job_name, int(params.get("pagina", 1) or 1), str(exc), None)
                return None, False

    def _persist_page(self, job_name: str, entity_name: str, page_data: PageData, *, auth_used: bool) -> None:
        request_params = dict(page_data.params)
        request_params["_auth_used"] = auth_used
        self.warehouse.land_page(
            run_id=self.run_id,
            job_name=job_name,
            entity_name=entity_name,
            page_number=page_data.page_number,
            request_params_json=stable_json(request_params),
            response_format=page_data.content_type or "json",
            http_status=page_data.status_code,
            payload_json=stable_json(page_data.raw),
            payload_text=page_data.raw if isinstance(page_data.raw, str) else None,
            payload_hash=stable_hash(page_data.raw),
        )

    def _job_has_pages(self, job_name: str) -> bool:
        if not self.config.bronze_db_path.exists():
            return False
        with self.warehouse.connect() as con:
            return bool(con.execute("select count(*) from bronze_pages where job_name = ?", [job_name]).fetchone()[0])

    def _load_job_records(self, job_name: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if not self.config.bronze_db_path.exists():
            return records
        with self.warehouse.connect() as con:
            rows = con.execute("select payload_json from bronze_pages where job_name = ? order by page_number, fetched_at", [job_name]).fetchall()
        for (payload_json,) in rows:
            try:
                records.extend(extract_records(json.loads(payload_json)))
            except json.JSONDecodeError:
                continue
        return records

    def _record_error(self, job_name: str, page_number: int | None, message: str, payload: Any) -> None:
        self.stats[job_name]["errors"] += 1
        payload_json = stable_json(payload) if payload is not None else None
        self.ops_store.record_error(run_id=self.run_id, job_name=job_name, page_number=page_number, message=message, payload_json=payload_json)
        self.errors.append({"job_name": job_name, "page_number": page_number, "message": message})
        self._log(f"  ERRO {job_name} page={page_number}: {message}")

    def _should_continue(self, page_data: PageData) -> bool:
        raw = page_data.raw
        if isinstance(raw, dict):
            if "paginasRestantes" in raw:
                return int(raw.get("paginasRestantes") or 0) > 0
            if "totalPaginas" in raw:
                return page_data.page_number < int(raw.get("totalPaginas") or 0)
        return bool(page_data.records)

    def _limited(self, values: list[str], max_count: int) -> list[str]:
        if max_count and len(values) > max_count:
            self._log(f"  limitando {len(values)} valores a {max_count}")
            return values[:max_count]
        return values

    def _log(self, message: str) -> None:
        if self.reporter is not None:
            handler = getattr(self.reporter, "message", None)
            if handler:
                handler(message)
                return
        print(message)


def sanitize(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_")[:160]


def first_present(row: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def unique_sorted(values: Iterable[Any]) -> list[str]:
    result: set[str] = set()
    for value in values:
        if value not in (None, ""):
            result.add(str(value))
    return sorted(result)


def run_full_city_crawl(config: FullCityConfig, *, reporter: Any | None = None) -> FullCityResult:
    return FullCityCrawler(config, reporter=reporter).run()
