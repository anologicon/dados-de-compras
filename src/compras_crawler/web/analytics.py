"""Rebuildable, read-only projections. Bronze remains the source of truth."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterator
import csv
import io
import json
import logging
import uuid

import duckdb

from ..normalize import extract_records, stable_hash, stable_json
from ..pncp_direct import control_incoherence, nested_first, parse_pncp_control
from .store import AppStore

PURCHASE_PNCP = {"pncp_contratacao", "pncp_contratacao_id"}
PURCHASE_LEGACY = {"licitacao", "licitacao_id", "pregao", "pregao_id", "compra_sem_licitacao", "compra_sem_licitacao_id", "rdc"}
FAMILIES = {
    **{e: "pncp" for e in PURCHASE_PNCP}, **{e: "legacy" for e in PURCHASE_LEGACY},
    "pncp_item_contratacao": "items", "pncp_resultado_item": "results",
    "pncp_direct_contratacao": "pncp", "pncp_direct_item_contratacao": "items",
    "pncp_direct_resultado_item": "results",
    "contrato": "contracts", "contrato_id": "contracts",
    "contrato_item": "contract_items", "contrato_item_id": "contract_items",
    "fornecedor": "suppliers", "price_material_detail": "prices", "price_service": "prices",
    "price_service_detail": "prices", "uasg": "units",
}


def item_reference(row: dict[str, Any]) -> tuple[str, Any] | None:
    """Explicit item number: the Compras.gov.br key first, then the PNCP direct one."""
    for key in ("numeroItemPncp", "numeroItem"):
        if row.get(key) is not None and row.get(key) != "":
            return key, row[key]
    return None


def _expand_nested(row: dict[str, Any]) -> dict[str, Any]:
    """Flat read view over nested PNCP-direct payloads. The stored payload stays raw.

    Endpoint parentage never becomes a body field: composite identity below is
    built only from what the body itself says.
    """
    view = dict(row)
    flat = (
        ("orgaoEntidadeCnpj", (row, ("orgaoEntidade", "cnpj"))),
        ("orgaoEntidadeRazaoSocial", (row, ("orgaoEntidade", "razaoSocial"))),
        ("unidadeOrgaoCodigoIbge", (row, ("unidadeOrgao", "codigoIbge"))),
        ("unidadeOrgaoCodigoUnidade", (row, ("unidadeOrgao", "codigoUnidade"))),
        ("niFornecedor", (row, ("fornecedor", "niFornecedor"))),
        ("tipoPessoa", (row, ("fornecedor", "tipoPessoa"))),
        ("nomeRazaoSocialFornecedor", (row, ("fornecedor", "nomeRazaoSocialFornecedor"))),
    )
    for key, args in flat:
        if view.get(key) in (None, ""):
            value = nested_first(*args)
            if key == "nomeRazaoSocialFornecedor" and value in (None, ""):
                value = nested_first(row, ("fornecedor", "razaoSocial"))
            if value is not None and value != "":
                view[key] = value
    return view


def first(row: dict[str, Any], *keys: str) -> Any:
    return next((row[k] for k in keys if row.get(k) is not None and row[k] != ""), None)


def number(value: Any) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    text = str(value).strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        value = Decimal(text)
        return value if value.is_finite() and abs(value) < Decimal("1e20") else None
    except InvalidOperation:
        return None


def day(value: Any) -> str | None:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (ValueError, TypeError):
        return None


def purchase_cancelled(row: dict[str, Any]) -> bool:
    status = str(first(row, "situacaoCompraNome", "situacaoCompraNomePncp", "situacaoCompra") or "")
    return bool(first(row, "dataCancelamentoPncp", "dataCancelamento")) or status.strip().casefold() in {
        "anulada", "anulado", "cancelada", "cancelado", "revogada", "revogado",
    }


def normalize(entity: str, row: dict[str, Any], origin: dict[str, Any]) -> list[Any]:
    if isinstance(row, dict) and entity.startswith("pncp_direct_"):
        view = _expand_nested(row)
    else:
        view = row
    family = FAMILIES.get(entity, entity)
    purchase_id = first(view, "idCompra", "id_compra")
    control = first(view, "numeroControlePNCP", "numeroControlePNCPCompra", "numeroControlePncpCompra")
    item_id = first(view, "idCompraItem")
    reference = item_reference(view)
    item_number = reference[1] if reference else None
    supplier = first(view, "niFornecedor", "cnpj", "cpf", "cnpjCpf", "codFornecedor")
    identity: Any = None
    if family in ("pncp", "legacy"):
        identity = purchase_id or (control if family == "pncp" else None)
    elif family == "items":
        parent = purchase_id or control
        identity = item_id or ([str(parent), str(item_number)] if parent is not None and item_number is not None else None)
    elif family == "results":
        sequence = view.get("sequencialResultado")
        if item_id is not None and sequence is not None:
            identity = [item_id, sequence]
        elif (purchase_id is not None or control is not None) and item_number is not None and sequence is not None:
            # Composite PNCP-direct identity. The body parent control (or the
            # detail purchase path) is explicit here; provenance never creates identity.
            identity = [str(purchase_id or control), str(item_number), str(sequence)]
    elif family == "contracts":
        identity = first(view, "numeroControlePncpContrato", "numeroControlePNCPContrato", "idContrato")
    elif family == "suppliers":
        identity = supplier
    elif family == "units":
        identity = first(view, "codigoUasg")
    identity_text = stable_json(identity) if identity is not None else None
    record_key = [family, identity_text or stable_hash(view)]
    if family == "pncp":
        # Collapse matching list/detail observations, not competing controls or
        # reports from different collection sources.
        record_key.extend([entity.startswith("pncp_direct_"), control])
    elif family in ("items", "results"):
        # The graph counts observations, not deduplicated child entities. Do
        # not overwrite a potentially different body from the other source.
        record_key.append(entity.startswith("pncp_direct_"))
    record_id = stable_hash(record_key)
    published = day(first(view, "dataPublicacaoPncp", "data_publicacao", "dt_data_edital"))
    city = first(view, "unidadeOrgaoCodigoIbge", "codigoMunicipioIbge")
    unit = first(view, "unidadeOrgaoCodigoUnidade", "codigoUasg", "co_uasg", "uasg")
    updated = str(first(view, "dataAtualizacaoPncp", "dataHoraInclusao") or "")
    excluded = first(view, "contratacaoExcluida", "contratoExcluido") in (True, "true", "True", 1)
    # Control vs body coherence (same rule as the collector: divergence only
    # counts when the body field is present). Incoherent controls never become
    # purchases in the projection; the exclusion reason stays explicit.
    is_direct_purchase = entity == "pncp_direct_contratacao"
    incoherent = (family == "pncp" and control is not None and bool(control_incoherence(control, view))
                  or is_direct_purchase and parse_pncp_control(control) is None)
    return [
        record_id, family, entity, identity_text, str(purchase_id) if purchase_id is not None else None,
        str(control) if control is not None else None, str(item_id) if item_id is not None else None,
        str(city) if city is not None else None, str(unit) if unit is not None else None,
        published, str(first(view, "orgaoEntidadeRazaoSocial", "nomeOrgao", "nome_orgao") or "Não informado"),
        str(first(view, "modalidadeNome", "nomeModalidadeCompra", "nomeModalidadeContratacao", "modalidade") or "Não informada"),
        str(first(view, "objetoCompra", "objeto", "objeto_licitacao", "ds_objeto", "descricaoResumida", "descricao", "nomeRazaoSocial") or ""),
        number(first(view, "valorTotalEstimado", "valor_estimado_total", "vl_estimado_total")),
        number(first(view, "valorTotalHomologado", "valor_homologado_total", "vl_homologado_total")),
        excluded, incoherent, family in ("pncp", "legacy") and purchase_cancelled(view),
        str(first(view, "codItemCatalogo", "codigoItemCatalogo") or ""),
        str(first(view, "materialOuServico", "tipoItem") or ""), str(first(view, "unidadeMedida", "unidadeFornecimento") or ""),
        str(supplier) if supplier is not None else None,
        str(first(view, "nomeRazaoSocialFornecedor", "nomeFornecedor", "nomeRazaoSocial") or ""),
        number(first(view, "quantidadeHomologada", "quantidadeResultado", "quantidade")),
        number(first(view, "valorUnitarioHomologado", "valorUnitarioResultado")),
        number(first(view, "valorUnitarioEstimado")), number(view.get("valorGlobal")),
        updated, origin["fetched_at"], stable_json(origin), stable_json(row),
    ]


def build_snapshot(store: AppStore, city_id: str, *, coverage: dict[str, Any] | None = None,
                   before_publish: Callable[[], None] | None = None,
                   publication_lease: tuple[str, str] | None = None) -> dict[str, Any]:
    city_dir = store.city_dir(city_id)
    bronze = city_dir / "bronze.duckdb"
    if not bronze.is_file():
        raise ValueError("o município ainda não possui dados Bronze")
    relative = f"cities/{city_id}/snapshots/{uuid.uuid4()}.duckdb"
    path = store.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(".jsonl")
    published = False
    try:
        with duckdb.connect(str(bronze), read_only=True) as source, duckdb.connect(str(path)) as target:
            source.execute("SET memory_limit='512MB'")
            source.execute("SET threads=2")
            target.execute("SET memory_limit='512MB'")
            target.execute("SET threads=2")
            target.execute("""CREATE TABLE observations (
                id TEXT, family TEXT, entity TEXT, identity TEXT, purchase_id TEXT, control TEXT, item_id TEXT,
                city_code TEXT, unit_code TEXT, published_on DATE, org_name TEXT, modality TEXT, description TEXT,
                estimated DECIMAL(24,4), awarded DECIMAL(24,4), excluded BOOLEAN, control_incoherent BOOLEAN,
                cancelled BOOLEAN, catalog_code TEXT, item_type TEXT, unit TEXT, supplier_id TEXT, supplier_name TEXT,
                quantity DECIMAL(24,4), unit_price DECIMAL(24,4), estimated_unit_price DECIMAL(24,4),
                contract_value DECIMAL(24,4), updated TEXT, fetched_at TEXT, origin_json TEXT, payload_json TEXT
            )""")
            entity_pages = {name: count for name, count in source.execute(
                "SELECT entity_name,count(*) FROM bronze_pages GROUP BY 1").fetchall()}
            columns = [row[0] for row in target.execute("DESCRIBE observations").fetchall()]
            cursor = source.execute("""SELECT run_id,job_name,entity_name,page_number,request_params_json,
                payload_json,fetched_at FROM bronze_pages ORDER BY fetched_at""")
            # Bounded staging avoids slow per-record SQL binding and needs no pandas/Arrow dependency.
            with staging.open("w", encoding="utf-8") as output:
                while True:
                    pages = cursor.fetchmany(30)
                    if not pages:
                        break
                    for run_id, job, entity, page, params, payload, fetched in pages:
                        parsed = json.loads(payload)
                        fetched_at = fetched.isoformat() if hasattr(fetched, "isoformat") else str(fetched)
                        for index, record in enumerate(extract_records(parsed)):
                            origin = dict(run_id=run_id, job=job, entity=entity, page=page, record_index=index,
                                          request_params=json.loads(params), fetched_at=fetched_at)
                            output.write(json.dumps(dict(zip(columns, normalize(entity, record, origin))),
                                                    default=str, ensure_ascii=False) + "\n")
            schema = "{" + ",".join(f"'{column}':'VARCHAR'" for column in columns) + "}"
            target.execute("INSERT INTO observations SELECT * FROM read_ndjson(?, columns=" + schema +
                           ", maximum_object_size=67108864)", [str(staging)])
            staging.unlink()
            # Ingestion time defines "latest observed". Do not compare an unknown
            # source-update timestamp with the ingestion clock as if they were the same axis.
            target.execute("""CREATE TABLE records AS SELECT * EXCLUDE (rank) FROM (
                SELECT *, row_number() OVER (PARTITION BY id ORDER BY fetched_at DESC, updated DESC,
                    CASE WHEN entity LIKE '%_id' THEN 1 ELSE 0 END DESC, payload_json DESC) rank FROM observations
                ) WHERE rank=1""")
            target.execute("DROP TABLE observations")
            # Only explicit municipality/UASG evidence is used. The filename is never geographic evidence.
            target.execute("""CREATE TABLE purchase_candidates AS
                WITH pairs AS (
                    SELECT DISTINCT control,purchase_id FROM records WHERE family IN ('pncp','legacy')
                    AND control IS NOT NULL AND purchase_id IS NOT NULL
                ), conflicting_ids AS (
                    SELECT purchase_id FROM pairs GROUP BY purchase_id HAVING count(*)>1
                ), conflicting_controls AS (
                    SELECT control FROM pairs GROUP BY control HAVING count(*)>1
                    UNION SELECT control FROM pairs WHERE purchase_id IN (SELECT purchase_id FROM conflicting_ids)
                ), aliases AS (
                    SELECT control,purchase_id FROM pairs WHERE control NOT IN (SELECT control FROM conflicting_controls)
                ), units AS (
                    SELECT unit_code,min(city_code) city_code FROM records WHERE family='units'
                    AND city_code IS NOT NULL GROUP BY unit_code HAVING count(DISTINCT city_code)=1
                ), candidates AS (
                    SELECT r.*, CASE WHEN coalesce(r.purchase_id,a.purchase_id) IS NOT NULL
                    THEN 'id:' || coalesce(r.purchase_id,a.purchase_id) ELSE 'pncp:' || r.control END purchase_key,
                    coalesce(r.city_code,u.city_code) resolved_city,
                    CASE WHEN starts_with(r.entity,'pncp_direct_') THEN 'pncp_direct' ELSE 'comprasgov' END collection_source,
                    CASE WHEN r.control IN (SELECT control FROM conflicting_controls)
                              OR r.purchase_id IN (SELECT purchase_id FROM conflicting_ids) THEN 'Identificadores conflitantes'
                          WHEN r.control_incoherent THEN 'Controle incoerente com o corpo'
                          WHEN r.identity IS NULL THEN 'Sem identificador seguro'
                          WHEN coalesce(r.city_code,u.city_code) IS NULL THEN 'Município não comprovado'
                         WHEN coalesce(r.city_code,u.city_code) <> ? THEN 'Outro município'
                         WHEN r.published_on IS NULL THEN 'Data de publicação desconhecida'
                         ELSE NULL END exclusion_reason
                    FROM records r LEFT JOIN aliases a ON a.control=r.control
                    LEFT JOIN units u ON u.unit_code=r.unit_code AND NOT starts_with(r.entity,'pncp_direct_')
                    WHERE r.family IN ('pncp','legacy')
                ), source_conflicts AS (
                    SELECT purchase_key, CASE
                        WHEN bool_or(control_incoherent) THEN 'Controle incoerente com o corpo'
                        WHEN count(DISTINCT resolved_city)>1 THEN 'Municípios conflitantes entre origens'
                        WHEN count(DISTINCT (excluded,cancelled))>1 THEN 'Cancelamento ou exclusão conflitante entre origens'
                    END reason
                    FROM candidates GROUP BY purchase_key HAVING count(DISTINCT collection_source)>1
                )
                SELECT c.* REPLACE (coalesce(s.reason,c.exclusion_reason) AS exclusion_reason)
                FROM candidates c LEFT JOIN source_conflicts s USING (purchase_key)""", [city_id])
            target.execute("""CREATE TABLE purchases AS SELECT * EXCLUDE(rank) FROM (
                SELECT *, row_number() OVER (PARTITION BY purchase_key ORDER BY
                     CASE WHEN collection_source='pncp_direct' THEN 2 WHEN family='pncp' THEN 1 ELSE 0 END DESC,
                     fetched_at DESC, updated DESC, id) rank
                FROM purchase_candidates
                 ) WHERE rank=1 AND NOT excluded AND NOT cancelled AND exclusion_reason IS NULL""")
            total = target.execute("SELECT count(*) FROM records").fetchone()[0]
            reasons = dict(target.execute("""SELECT exclusion_reason,count(*) FROM purchase_candidates
                WHERE exclusion_reason IS NOT NULL AND exclusion_reason <> 'Outro município'
                GROUP BY exclusion_reason ORDER BY exclusion_reason""").fetchall())
            summary = dict(status="unverified", message="Importação: cobertura e conclusão da coleta de origem não verificadas.",
                           entity_pages=entity_pages, records=total, unreconciled=sum(reasons.values()),
                           exclusion_reasons=reasons,
                           snapshot_built_at=datetime.now(timezone.utc).isoformat())
            summary.update(coverage or {})
            target.execute("CREATE TABLE snapshot_metadata (value TEXT)")
            target.execute("INSERT INTO snapshot_metadata VALUES (?)", [stable_json(summary)])
        if before_publish:
            before_publish()
        retired = store.publish(city_id, relative, summary, lease=publication_lease)
        published = True
        if retired and retired != relative:
            # Cleanup failure must never invalidate the newly published snapshot.
            retired_path = (store.root / retired).resolve()
            if retired_path.is_relative_to((city_dir / "snapshots").resolve()):
                try:
                    retired_path.unlink(missing_ok=True)
                except OSError as exc:
                    logging.getLogger(__name__).warning("Could not retire projection: %s", exc)
        return summary
    except BaseException:
        if not published:
            path.unlink(missing_ok=True)
            Path(str(path) + ".wal").unlink(missing_ok=True)
        raise
    finally:
        staging.unlink(missing_ok=True)


def snapshot_path(store: AppStore, city_id: str) -> Path:
    city = store.city(city_id)
    if not city["snapshot"]:
        raise ValueError("aguardando a primeira coleta ou importação")
    path = (store.root / city["snapshot"]).resolve()
    if not path.is_relative_to(store.root):
        raise ValueError("invalid snapshot path")
    return path


def connection(store: AppStore, city_id: str):
    con = duckdb.connect(str(snapshot_path(store, city_id)), read_only=True)
    con.execute("SET memory_limit='512MB'")
    con.execute("SET threads=2")
    return con


def where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses, values = ["true"], []
    for field, operator, key in (("published_on", ">=", "start_date"), ("published_on", "<=", "end_date"), ("modality", "=", "modality"), ("org_name", "=", "org_name")):
        if filters.get(key):
            clauses.append(f"{field} {operator} ?")
            values.append(filters[key])
    if filters.get("q"):
        clauses.append("(contains(lower(description),lower(?)) OR contains(lower(org_name),lower(?)) OR contains(lower(purchase_key),lower(?)))")
        values.extend([filters["q"]] * 3)
    return " AND ".join(clauses), values


def rows(con, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    cursor = con.execute(sql, params or [])
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def overview(store: AppStore, city_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    condition, params = where(filters)
    with connection(store, city_id) as con:
        metrics = rows(con, f"""SELECT count(*) purchases, sum(estimated) estimated, sum(awarded) awarded,
            count(estimated) estimated_known, count(awarded) awarded_known,
            count(DISTINCT org_name) FILTER (WHERE org_name <> 'Não informado') organizations,
            count(*) FILTER (WHERE org_name <> 'Não informado') organization_known,
            count(*) FILTER (WHERE modality <> 'Não informada') modality_known
            FROM purchases WHERE {condition}""", params)[0]
        monthly = rows(con, f"""SELECT strftime(published_on,'%Y-%m') AS month,count(*) purchases,
            sum(estimated) estimated,sum(awarded) awarded,
            count(estimated) estimated_known,count(awarded) awarded_known
            FROM purchases WHERE {condition} GROUP BY 1 ORDER BY 1""", params)
        # Keep the complete groups: rankings by value must not be restricted to the
        # leaders by volume. The UI chooses its top N only after selecting a measure.
        organizations = rows(con, f"""SELECT org_name,count(*) purchases,
            sum(estimated) estimated,sum(awarded) awarded,
            count(estimated) estimated_known,count(awarded) awarded_known
            FROM purchases WHERE {condition} GROUP BY 1 ORDER BY org_name""", params)
        modality_breakdown = rows(con, f"""SELECT modality,count(*) purchases,
            sum(estimated) estimated,sum(awarded) awarded,
            count(estimated) estimated_known,count(awarded) awarded_known
            FROM purchases WHERE {condition} GROUP BY 1 ORDER BY purchases DESC,modality""", params)
        sources = rows(con, f"""SELECT family,count(*) purchases FROM purchases
            WHERE {condition} GROUP BY 1 ORDER BY family""", params)
        filtered_range = rows(con, f"""SELECT min(published_on) start_date,max(published_on) end_date
            FROM purchases WHERE {condition}""", params)[0]
        modalities = rows(con, "SELECT DISTINCT modality FROM purchases ORDER BY 1")
        orgs = rows(con, "SELECT DISTINCT org_name FROM purchases ORDER BY 1")
        coverage = json.loads(con.execute("SELECT value FROM snapshot_metadata").fetchone()[0])
        date_range = rows(con, "SELECT min(published_on) start_date,max(published_on) end_date FROM purchases")[0]
    return dict(metrics=metrics, monthly=monthly, organizations=organizations, modalities=modalities,
                modality_breakdown=modality_breakdown, sources=sources, filtered_range=filtered_range,
                orgs=orgs, coverage=coverage, date_range=date_range)


PURCHASE_COLUMNS = "purchase_key,family,published_on,org_name,modality,description,estimated,awarded,origin_json,payload_json"


def purchases(store: AppStore, city_id: str, filters: dict[str, Any], page: int, page_size: int) -> dict[str, Any]:
    condition, params = where(filters)
    with connection(store, city_id) as con:
        total = con.execute(f"SELECT count(*) FROM purchases WHERE {condition}", params).fetchone()[0]
        data = rows(con, f"SELECT {PURCHASE_COLUMNS} FROM purchases WHERE {condition} ORDER BY published_on DESC,purchase_key LIMIT ? OFFSET ?",
                    params + [page_size, (page - 1) * page_size])
    return dict(items=data, total=total, page=page, page_size=page_size)


def entities(store: AppStore, city_id: str) -> list[dict[str, Any]]:
    with connection(store, city_id) as con:
        return rows(con, "SELECT entity,count(*) records FROM records GROUP BY 1 ORDER BY 1")


def raw_records(store: AppStore, city_id: str, entity: str, q: str, page: int, page_size: int) -> dict[str, Any]:
    with connection(store, city_id) as con:
        condition = "entity=? AND (contains(lower(payload_json),lower(?)))"
        total = con.execute(f"SELECT count(*) FROM records WHERE {condition}", [entity, q]).fetchone()[0]
        data = rows(con, f"SELECT id,entity,payload_json,origin_json FROM records WHERE {condition} ORDER BY id LIMIT ? OFFSET ?",
                    [entity, q, page_size, (page - 1) * page_size])
    return dict(items=data, total=total, page=page, page_size=page_size)


def safe_csv(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def export_purchases(store: AppStore, city_id: str, filters: dict[str, Any], fmt: str) -> Iterator[str]:
    """Stream the whole filtered population in bounded batches, not just a UI page."""
    condition, params = where(filters)
    with connection(store, city_id) as con:
        coverage = json.loads(con.execute("SELECT value FROM snapshot_metadata").fetchone()[0])
        cursor = con.execute(f"SELECT {PURCHASE_COLUMNS} FROM purchases WHERE {condition} ORDER BY published_on DESC,purchase_key", params)
        columns = [d[0] for d in cursor.description]
        if fmt == "json":
            yield '{"metadata":' + json.dumps(dict(city_id=city_id, filters=filters, coverage=coverage), default=str, ensure_ascii=False) + ',"records":['
        else:
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns + ["snapshot_built_at", "coverage_status", "filters_json"])
            yield "\ufeff" + buffer.getvalue()
        separator = ""
        while True:
            batch = cursor.fetchmany(200)
            if not batch:
                break
            if fmt == "json":
                for row in batch:
                    record = dict(zip(columns, row))
                    record["origin"] = json.loads(record.pop("origin_json"))
                    record["original"] = json.loads(record.pop("payload_json"))
                    yield separator + json.dumps(record, ensure_ascii=False, default=str)
                    separator = ","
            else:
                buffer.seek(0)
                buffer.truncate(0)
                for row in batch:
                    writer.writerow([safe_csv(value) for value in row] + [coverage["snapshot_built_at"], coverage["status"], json.dumps(filters, ensure_ascii=False, default=str)])
                yield buffer.getvalue()
        if fmt == "json":
            yield "]}"
