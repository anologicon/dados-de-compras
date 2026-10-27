"""Read-only, evidence-based navigation over already published snapshots.

No schema migration or Bronze access. Missing/contradictory identifiers are not
repaired by names, catalog codes or position in a response. Counts describe
observed records, not payments or a complete universe of awards/suppliers.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
import json
import re

from .analytics import PURCHASE_COLUMNS, connection, first, number, rows
from .store import AppStore


class SnapshotChanged(ValueError):
    pass


def link(status: str, reason: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return dict(status=status, reason=reason, evidence=evidence or [])


def text(value: Any) -> str | None:
    return str(value) if value is not None and value != "" else None


def flag(value: Any) -> bool | None:
    if value in (True, 1, "true", "True"):
        return True
    if value in (False, 0, "false", "False"):
        return False
    return None


def document(value: Any, person_type: Any = None) -> tuple[str, str] | None:
    """Normalize only domestic document formatting, never pad or guess IDs."""
    raw = text(value)
    if not raw or not re.fullmatch(r"[0-9.\-/\s]+", raw):
        return None
    digits = re.sub(r"[.\-/\s]", "", raw)
    kind = {11: "cpf", 14: "cnpj"}.get(len(digits))
    person = str(person_type or "").upper()
    if person and person not in ("PF", "PJ", "F", "J"):
        return None
    if person in ("PF", "F") and kind != "cpf":
        return None
    if person in ("PJ", "J") and kind != "cnpj":
        return None
    return (kind, digits) if kind else None


def display_document(doc: tuple[str, str] | None) -> str:
    if not doc:
        return "Identificador não conciliado"
    kind, digits = doc
    if kind == "cpf":
        return "***.***.***-" + digits[-2:]
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def page(items: list[dict[str, Any]], current: int, size: int) -> dict[str, Any]:
    return dict(items=items[(current - 1) * size:current * size], total=len(items), page=current, page_size=size)


def _matching(column: str, values: set[str], params: list[Any]) -> str:
    if not values:
        return "false"
    ordered = sorted(values)
    params.extend(ordered)
    return column + " IN (" + ",".join("?" for _ in ordered) + ")"


class PurchaseGraph:
    def __init__(self, con, purchase_key: str, snapshot: str | None):
        self.coverage = json.loads(con.execute("SELECT value FROM snapshot_metadata").fetchone()[0])
        self.snapshot = self.coverage["snapshot_built_at"]
        if snapshot is not None and snapshot != self.snapshot:
            raise SnapshotChanged("O snapshot mudou. Atualize a ficha para não misturar versões dos dados.")
        found = rows(con, "SELECT * FROM purchases WHERE purchase_key=?", [purchase_key])
        if not found:
            raise KeyError("Compra não encontrada no snapshot atual.")
        self.purchase = found[0]
        self.key = purchase_key
        aliases = rows(con, """SELECT purchase_id,control FROM purchase_candidates
            WHERE purchase_key=? AND exclusion_reason IS NULL AND NOT excluded""", [purchase_key])
        self.purchase_ids = {str(r["purchase_id"]) for r in aliases if r["purchase_id"] is not None}
        self.controls = {str(r["control"]) for r in aliases if r["control"] is not None}
        self.control_owners: dict[str, set[str]] = defaultdict(set)
        for row in rows(con, "SELECT DISTINCT control,purchase_key FROM purchase_candidates WHERE control IS NOT NULL"):
            self.control_owners[row["control"]].add(row["purchase_key"])
        params: list[Any] = []
        condition = self._parent_condition(params)
        self.items = rows(con, f"""SELECT * FROM records WHERE family='items' AND ({condition})
            ORDER BY try_cast(json_extract_string(payload_json,'$.numeroItemPncp') AS BIGINT) NULLS LAST,id""", params)
        self.item_links = {r["id"]: self.parent_link(r) for r in self.items}
        item_ids = {r["item_id"] for r in self.items if r["item_id"] is not None}
        # Check the item identifier across the snapshot, not only in the current
        # purchase's candidate set. Contradictory owners cannot be silently joined.
        item_params: list[Any] = []
        item_condition = _matching("item_id", item_ids, item_params)
        all_items = rows(con, f"SELECT * FROM records WHERE family='items' AND ({item_condition})", item_params)
        self.by_item_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_number: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in all_items:
            self.by_item_id[item["item_id"]].append(item)
        for item in self.items:
            if self.item_links[item["id"]]["status"] == "confirmed":
                item_number = text(json.loads(item["payload_json"]).get("numeroItemPncp"))
                if item_number is not None:
                    self.by_number[item_number].append(item)
        result_params: list[Any] = []
        parent_condition = self._parent_condition(result_params)
        item_condition = _matching("item_id", item_ids, result_params)
        self.results = rows(con, f"""SELECT * FROM records WHERE family='results'
            AND ({parent_condition} OR {item_condition})
            ORDER BY try_cast(json_extract_string(payload_json,'$.numeroItemPncp') AS BIGINT) NULLS LAST,
                     try_cast(json_extract_string(payload_json,'$.sequencialResultado') AS BIGINT) NULLS LAST,id""", result_params)
        self.result_links = {r["id"]: self.resolve_result(r) for r in self.results}

    def _parent_condition(self, params: list[Any]) -> str:
        return _matching("purchase_id", self.purchase_ids, params) + " OR " + _matching("control", self.controls, params)

    def parent_link(self, row: dict[str, Any]) -> dict[str, Any]:
        evidence = []
        if row["purchase_id"] in self.purchase_ids:
            evidence.append("idCompra")
        if row["control"] in self.controls:
            evidence.append("numeroControlePNCPCompra")
        if not evidence:
            return link("missing", "Sem identificador explícito que vincule o registro a esta compra.")
        contradictions = self.contradictions(row)
        if contradictions:
            return link("ambiguous", "; ".join(contradictions) + ". Vínculo não confirmado.", evidence)
        return link("confirmed", "Identificadores explícitos compatíveis com a compra.", evidence)

    def contradictions(self, row: dict[str, Any]) -> list[str]:
        reasons = []
        if row["city_code"] is not None and row["city_code"] != self.purchase["resolved_city"]:
            reasons.append("município explícito divergente")
        if row["purchase_id"] is not None and self.purchase_ids and row["purchase_id"] not in self.purchase_ids:
            reasons.append("idCompra divergente")
        if row["control"] is not None:
            if self.controls and row["control"] not in self.controls:
                reasons.append("controle PNCP divergente")
            if self.control_owners[row["control"]] - {self.key}:
                reasons.append("controle PNCP associado a outra compra ou a identificadores conflitantes")
        return reasons

    def resolve_result(self, row: dict[str, Any]) -> dict[str, Any]:
        parent = self.parent_link(row)
        payload = json.loads(row["payload_json"])
        candidates = []
        evidence = []
        if row["item_id"] is not None:
            candidates = self.by_item_id[row["item_id"]]
            evidence = ["idCompraItem"]
        elif parent["status"] == "confirmed":
            item_number = text(payload.get("numeroItemPncp"))
            if item_number is not None:
                candidates = self.by_number[item_number]
                evidence = parent["evidence"] + ["numeroItemPncp"]
        related = None
        item_link = link("missing", "Nenhum item com identificadores compatíveis foi encontrado neste snapshot.")
        if candidates:
            candidate_links = [self.parent_link(item) for item in candidates]
            if (len(candidates) == 1 and candidate_links[0]["status"] == "confirmed"
                    and parent["status"] != "ambiguous"):
                candidate = candidates[0]
                # An explicit foreign parent must not be overridden by item ID.
                conflicting = bool(self.contradictions(row))
                result_number = text(payload.get("numeroItemPncp"))
                candidate_number = text(json.loads(candidate["payload_json"]).get("numeroItemPncp"))
                if conflicting or (result_number is not None and candidate_number is not None and result_number != candidate_number):
                    item_link = link("ambiguous", "O identificador do item conflita com a compra ou com o número do item.", evidence)
                    parent = link("ambiguous", "Resultado com identificadores contraditórios; associação não confirmada.", evidence)
                else:
                    related = candidate["id"]
                    item_link = link("confirmed", "Item identificado de forma única por identificadores explícitos.", evidence)
                    if parent["status"] == "missing":
                        parent = link("confirmed", "Compra confirmada por item com vínculo explícito e único.", ["idCompraItem"])
            else:
                item_link = link("ambiguous", "O identificador não aponta de forma única para um item confirmado desta compra.", evidence)
                if parent["status"] == "missing":
                    parent = link("ambiguous", "A única referência é um item com associação não confirmada.", evidence)
        return dict(purchase_link=parent, item_link=item_link, item_record_id=related)

    def public_item(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        confirmed = sum(1 for relation in self.result_links.values() if relation["item_record_id"] == row["id"]
                        and relation["purchase_link"]["status"] == "confirmed")
        return dict(id=row["id"], identity_status="identified" if row["identity"] is not None else "unverified",
                    description=row["description"], item_number=text(payload.get("numeroItemPncp")),
                    catalog_code=row["catalog_code"] or None, item_type=row["item_type"] or None,
                    unit=row["unit"] or None, quantity=number(payload.get("quantidade")),
                    estimated_unit_price=row["estimated_unit_price"], status=text(payload.get("situacaoCompraItemNome")),
                    purchase_link=self.item_links[row["id"]], confirmed_results=confirmed,
                    payload_json=row["payload_json"], origin_json=row["origin_json"])

    def public_result(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        relation = self.result_links[row["id"]]
        doc = document(payload.get("niFornecedor"), payload.get("tipoPessoa"))
        return dict(id=row["id"], identity_status="identified" if row["identity"] is not None else "unverified",
                    **relation, item_number=text(payload.get("numeroItemPncp")),
                    sequence=text(payload.get("sequencialResultado")),
                    status=text(payload.get("situacaoCompraItemResultadoNome")),
                    cancelled=bool(payload.get("dataCancelamentoPncp")) or str(payload.get("situacaoCompraItemResultadoNome", "")).casefold() in ("cancelado", "cancelada"), quantity=row["quantity"],
                    unit_price=row["unit_price"], total=number(payload.get("valorTotalHomologado")),
                    supplier=dict(name=row["supplier_name"] or "Fornecedor não informado", identifier=display_document(doc),
                                  kind=doc[0] if doc else None,
                                  can_open=doc is not None and relation["purchase_link"]["status"] == "confirmed"),
                    payload_json=row["payload_json"], origin_json=row["origin_json"])

    def summary(self) -> dict[str, Any]:
        return dict(item_records=len(self.items), result_records=len(self.results),
                    confirmed_items=sum(v["status"] == "confirmed" for v in self.item_links.values()),
                    ambiguous_items=sum(v["status"] == "ambiguous" for v in self.item_links.values()),
                    confirmed_results=sum(v["purchase_link"]["status"] == "confirmed" for v in self.result_links.values()),
                    ambiguous_results=sum(v["purchase_link"]["status"] == "ambiguous" or v["item_link"]["status"] == "ambiguous" for v in self.result_links.values()),
                    results_without_item=sum(v["item_link"]["status"] != "confirmed" for v in self.result_links.values()))


def purchase_detail(store: AppStore, city_id: str, purchase_key: str) -> dict[str, Any]:
    with connection(store, city_id) as con:
        graph = PurchaseGraph(con, purchase_key, None)
        purchase = {key: graph.purchase[key] for key in PURCHASE_COLUMNS.split(",")}
        return dict(purchase=purchase, snapshot=graph.snapshot, coverage=graph.coverage, summary=graph.summary())


def purchase_items(store: AppStore, city_id: str, purchase_key: str, snapshot: str,
                   current: int = 1, size: int = 20) -> dict[str, Any]:
    with connection(store, city_id) as con:
        graph = PurchaseGraph(con, purchase_key, snapshot)
        selected = page(graph.items, current, size)
        selected["items"] = [graph.public_item(row) for row in selected["items"]]
        return dict(**selected, snapshot=graph.snapshot)


def purchase_results(store: AppStore, city_id: str, purchase_key: str, snapshot: str,
                     item_record_id: str | None = None, current: int = 1, size: int = 20) -> dict[str, Any]:
    with connection(store, city_id) as con:
        graph = PurchaseGraph(con, purchase_key, snapshot)
        selected = graph.results
        if item_record_id is not None:
            if item_record_id not in graph.item_links:
                raise KeyError("Item não encontrado entre os registros desta compra.")
            if graph.item_links[item_record_id]["status"] != "confirmed":
                raise ValueError("O vínculo deste item com a compra não está confirmado.")
            selected = [row for row in selected if graph.result_links[row["id"]]["item_record_id"] == item_record_id]
        result = page(selected, current, size)
        result["items"] = [graph.public_result(row) for row in result["items"]]
        return dict(**result, snapshot=graph.snapshot)


def supplier_detail(store: AppStore, city_id: str, purchase_key: str, snapshot: str,
                    result_id: str, current: int = 1, size: int = 10) -> dict[str, Any]:
    with connection(store, city_id) as con:
        graph = PurchaseGraph(con, purchase_key, snapshot)
        result = next((row for row in graph.results if row["id"] == result_id), None)
        if result is None:
            raise KeyError("Resultado não encontrado entre os registros desta compra.")
        if graph.result_links[result_id]["purchase_link"]["status"] != "confirmed":
            raise ValueError("O vínculo do resultado com esta compra não está confirmado.")
        payload = json.loads(result["payload_json"])
        doc = document(payload.get("niFornecedor"), payload.get("tipoPessoa"))
        if not doc:
            raise ValueError("O documento do fornecedor não permite uma conciliação cadastral segura.")
        # Read only the supplier reference family in the same published snapshot.
        # Formatting can differ; type and all digits must match. Names are not keys.
        registrations = []
        for row in rows(con, "SELECT id,payload_json,origin_json,fetched_at FROM records WHERE family='suppliers' ORDER BY id"):
            record = json.loads(row["payload_json"])
            provided = [key for key in ("cnpj", "cpf") if record.get(key) not in (None, "")]
            docs = [candidate for key in provided
                    if (candidate := document(record.get(key), "PJ" if key == "cnpj" else "PF"))]
            if doc not in docs:
                continue
            registrations.append(dict(id=row["id"], name=text(record.get("nomeRazaoSocialFornecedor")),
                                      cnae=text(record.get("nomeCnae")), size=text(record.get("porteEmpresaNome")),
                                      municipality=text(record.get("nomeMunicipio")), uf=text(record.get("ufSigla")),
                                      active=flag(record.get("ativo")), eligible=flag(record.get("habilitadoLicitar")),
                                      identity_conflict=len(docs) != 1 or len(provided) != 1, fetched_at=row["fetched_at"],
                                      payload_json=row["payload_json"], origin_json=row["origin_json"]))
        status = "missing" if not registrations else "ambiguous" if len(registrations) != 1 or registrations[0]["identity_conflict"] else "confirmed"
        return dict(supplier=graph.public_result(result)["supplier"], result=graph.public_result(result),
                    registration_status=status, registrations=page(registrations, current, size),
                    snapshot=graph.snapshot, coverage=graph.coverage)
