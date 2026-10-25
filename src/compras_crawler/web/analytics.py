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
from .store import AppStore

PURCHASE_PNCP = {"pncp_contratacao", "pncp_contratacao_id"}
PURCHASE_LEGACY = {"licitacao", "licitacao_id", "pregao", "pregao_id", "compra_sem_licitacao", "compra_sem_licitacao_id", "rdc"}
FAMILIES = {
    **{e: "pncp" for e in PURCHASE_PNCP}, **{e: "legacy" for e in PURCHASE_LEGACY},
    "pncp_item_contratacao": "items", "pncp_resultado_item": "results",
    "contrato": "contracts", "contrato_id": "contracts",
    "contrato_item": "contract_items", "contrato_item_id": "contract_items",
    "fornecedor": "suppliers", "price_material_detail": "prices", "price_service": "prices",
    "price_service_detail": "prices", "uasg": "units",
}


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


def normalize(entity: str, row: dict[str, Any], origin: dict[str, Any]) -> list[Any]:
    family = FAMILIES.get(entity, entity)
    purchase_id = first(row, "idCompra", "id_compra")
    control = first(row, "numeroControlePNCP", "numeroControlePNCPCompra", "numeroControlePncpCompra")
    item_id = first(row, "idCompraItem")
    supplier = first(row, "niFornecedor", "cnpj", "cpf", "cnpjCpf", "codFornecedor")
    identity: Any = None
    if family in ("pncp", "legacy"):
        identity = purchase_id or (control if family == "pncp" else None)
    elif family == "items":
        identity = item_id or ([purchase_id or control, row.get("numeroItemPncp")] if (purchase_id or control) and row.get("numeroItemPncp") is not None else None)
    elif family == "results":
        if item_id and row.get("sequencialResultado") is not None:
            identity = [item_id, row["sequencialResultado"]]
    elif family == "contracts":
        identity = first(row, "numeroControlePncpContrato", "numeroControlePNCPContrato", "idContrato")
    elif family == "suppliers":
        identity = supplier
    elif family == "units":
        identity = first(row, "codigoUasg")
    identity_text = stable_json(identity) if identity is not None else None
    record_id = stable_hash([family, identity_text or stable_hash(row)])
    published = day(first(row, "dataPublicacaoPncp", "data_publicacao", "dt_data_edital"))
    city = first(row, "unidadeOrgaoCodigoIbge", "codigoMunicipioIbge")
    unit = first(row, "unidadeOrgaoCodigoUnidade", "codigoUasg", "co_uasg", "uasg")
    updated = str(first(row, "dataAtualizacaoPncp", "dataHoraInclusao") or "")
    excluded = first(row, "contratacaoExcluida", "contratoExcluido") in (True, "true", "True", 1)
    return [
        record_id, family, entity, identity_text, str(purchase_id) if purchase_id is not None else None,
        str(control) if control is not None else None, str(item_id) if item_id is not None else None,
        str(city) if city is not None else None, str(unit) if unit is not None else None,
        published, str(first(row, "orgaoEntidadeRazaoSocial", "nomeOrgao", "nome_orgao") or "Não informado"),
        str(first(row, "modalidadeNome", "nomeModalidadeCompra", "modalidade") or "Não informada"),
        str(first(row, "objetoCompra", "objeto", "objeto_licitacao", "ds_objeto", "descricaoResumida", "descricao", "nomeRazaoSocial") or ""),
        number(first(row, "valorTotalEstimado", "valor_estimado_total", "vl_estimado_total")),
        number(first(row, "valorTotalHomologado", "valor_homologado_total", "vl_homologado_total")),
        excluded, str(first(row, "codItemCatalogo", "codigoItemCatalogo") or ""),
        str(first(row, "materialOuServico", "tipoItem") or ""), str(first(row, "unidadeMedida", "unidadeFornecimento") or ""),
        str(supplier) if supplier is not None else None,
        str(first(row, "nomeRazaoSocialFornecedor", "nomeFornecedor", "nomeRazaoSocial") or ""),
        number(first(row, "quantidadeHomologada", "quantidadeResultado", "quantidade")),
        number(first(row, "valorUnitarioHomologado", "valorUnitarioResultado")),
        number(first(row, "valorUnitarioEstimado")), number(row.get("valorGlobal")),
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
                estimated DECIMAL(24,4), awarded DECIMAL(24,4), excluded BOOLEAN,
                catalog_code TEXT, item_type TEXT, unit TEXT, supplier_id TEXT, supplier_name TEXT,
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
                WITH aliases AS (
                    SELECT control, min(purchase_id) purchase_id FROM records WHERE family='pncp'
                    AND control IS NOT NULL AND purchase_id IS NOT NULL GROUP BY control HAVING count(DISTINCT purchase_id)=1
                ), conflicts AS (
                    SELECT control FROM records WHERE family='pncp' AND control IS NOT NULL
                    AND purchase_id IS NOT NULL GROUP BY control HAVING count(DISTINCT purchase_id)>1
                ), units AS (
                    SELECT unit_code,min(city_code) city_code FROM records WHERE family='units'
                    AND city_code IS NOT NULL GROUP BY unit_code HAVING count(DISTINCT city_code)=1
                )
                SELECT r.*, CASE WHEN coalesce(r.purchase_id,a.purchase_id) IS NOT NULL
                    THEN 'id:' || coalesce(r.purchase_id,a.purchase_id) ELSE 'pncp:' || r.control END purchase_key,
                    coalesce(r.city_code,u.city_code) resolved_city,
                    CASE WHEN r.control IN (SELECT control FROM conflicts) THEN 'Identificadores conflitantes'
                         WHEN r.identity IS NULL THEN 'Sem identificador seguro'
                         WHEN coalesce(r.city_code,u.city_code) IS NULL THEN 'Município não comprovado'
                         WHEN coalesce(r.city_code,u.city_code) <> ? THEN 'Outro município'
                         WHEN r.published_on IS NULL THEN 'Data de publicação desconhecida'
                         ELSE NULL END exclusion_reason
                FROM records r LEFT JOIN aliases a ON a.control=r.control LEFT JOIN units u ON u.unit_code=r.unit_code
                WHERE r.family IN ('pncp','legacy')""", [city_id])
            target.execute("""CREATE TABLE purchases AS SELECT * EXCLUDE(rank) FROM (
                SELECT *, row_number() OVER (PARTITION BY purchase_key ORDER BY
                    CASE WHEN family='pncp' THEN 1 ELSE 0 END DESC, fetched_at DESC, updated DESC) rank
                FROM purchase_candidates
                ) WHERE rank=1 AND NOT excluded AND exclusion_reason IS NULL""")
            total = target.execute("SELECT count(*) FROM records").fetchone()[0]
            uncertain = target.execute("SELECT count(*) FROM purchase_candidates WHERE exclusion_reason IS NOT NULL AND exclusion_reason <> 'Outro município'").fetchone()[0]
            summary = dict(status="unverified", message="Importação: cobertura e conclusão da coleta de origem não verificadas.",
                           entity_pages=entity_pages, records=total, unreconciled=uncertain,
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
            count(DISTINCT org_name) organizations FROM purchases WHERE {condition}""", params)[0]
        monthly = rows(con, f"""SELECT strftime(published_on,'%Y-%m') AS month,count(*) purchases,
            sum(estimated) estimated,sum(awarded) awarded FROM purchases WHERE {condition} GROUP BY 1 ORDER BY 1""", params)
        organizations = rows(con, f"""SELECT org_name,count(*) purchases,sum(awarded) awarded
            FROM purchases WHERE {condition} GROUP BY 1 ORDER BY purchases DESC LIMIT 8""", params)
        modalities = rows(con, "SELECT DISTINCT modality FROM purchases ORDER BY 1")
        orgs = rows(con, "SELECT DISTINCT org_name FROM purchases ORDER BY 1")
        coverage = json.loads(con.execute("SELECT value FROM snapshot_metadata").fetchone()[0])
        date_range = rows(con, "SELECT min(published_on) start_date,max(published_on) end_date FROM purchases")[0]
    return dict(metrics=metrics, monthly=monthly, organizations=organizations, modalities=modalities,
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
