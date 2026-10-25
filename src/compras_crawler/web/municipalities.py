"""Official IBGE municipality lookup with a persistent, atomically replaced cache."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from typing import Any
import sqlite3
import unicodedata

import requests

from .locations import UF_CODES
from .store import AppStore, stamp

IBGE_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?orderBy=nome"
CACHE_TTL = timedelta(days=30)
UNAVAILABLE = "IBGE indisponível e sem catálogo oficial salvo. Tente novamente em instantes."


def search_text(value: str) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                            if not unicodedata.combining(c)).split())


class CatalogUnavailable(Exception):
    pass


class MunicipalityCatalog:
    def __init__(self, store: AppStore):
        self.store = store
        self._lock = Lock()
        self._retry_after = 0.0
        self._last_attempt = float("-inf")

    def init_schema(self) -> None:
        with self.store.connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS ibge_municipalities (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, uf TEXT NOT NULL,
                    search_name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ibge_catalog (
                    id INTEGER PRIMARY KEY CHECK(id=1), fetched_at TEXT NOT NULL
                );
            """)

    def _download(self) -> Any:
        # Fixed official URL, no bearer token and no user-controlled destination/redirect.
        response = requests.get(IBGE_URL, timeout=(5, 15), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError("IBGE did not return HTTP 200")
        return response.json()

    @staticmethod
    def _parse(payload: Any) -> list[tuple[str, str, str, str]]:
        if not isinstance(payload, list) or not payload:
            raise ValueError("empty or invalid IBGE catalog")
        states = {code: uf for uf, code in UF_CODES.items()}
        rows, seen = [], set()
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("invalid IBGE municipality")
            code, name = str(item.get("id", "")), item.get("nome")
            if (len(code) != 7 or not code.isascii() or not code.isdigit()
                    or code[:2] not in states or not isinstance(name, str)
                    or not 2 <= len(name.strip()) <= 100 or code in seen):
                raise ValueError("invalid or duplicated IBGE municipality")
            # The official numeric prefix remains usable when the API's regional
            # hierarchy is null (as happens with newly created municipalities).
            rows.append((code, name.strip(), states[code[:2]], search_text(name)))
            seen.add(code)
        return rows

    def _replace(self, rows: list[tuple[str, str, str, str]]) -> str:
        fetched_at = stamp()
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM ibge_municipalities")
            con.executemany("INSERT INTO ibge_municipalities VALUES (?,?,?,?)", rows)
            con.execute("INSERT OR REPLACE INTO ibge_catalog VALUES (1,?)", [fetched_at])
            con.execute("COMMIT")
        return fetched_at

    def ensure(self, *, refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            with self.store.connect() as con:
                row = con.execute("SELECT fetched_at FROM ibge_catalog WHERE id=1").fetchone()
            fetched_at = row[0] if row else None
            fresh = fetched_at and datetime.now(timezone.utc) - datetime.fromisoformat(fetched_at) < CACHE_TTL
            if fresh and not refresh:
                return dict(source="cache", fetched_at=fetched_at, warning=None)
            now = monotonic()
            # Typing must not hammer an unavailable API. Explicit retries may
            # bypass the failure cooldown, but never send more than one request/s.
            allowed = now >= self._retry_after or refresh
            warning = None
            failure = UNAVAILABLE
            if allowed and now - self._last_attempt >= 1:
                self._last_attempt = now
                try:
                    rows = self._parse(self._download())
                    updated_at = self._replace(rows)
                except (requests.RequestException, ValueError, TypeError):
                    warning = "Não foi possível atualizar o IBGE; usando o catálogo oficial salvo."
                    self._retry_after = monotonic() + 30
                except sqlite3.Error:
                    failure = "Não foi possível salvar o catálogo do IBGE. Verifique o espaço e as permissões do workspace."
                    warning = "Não foi possível salvar a atualização; usando o catálogo oficial anterior."
                    self._retry_after = monotonic() + 30
                else:
                    self._retry_after = 0
                    return dict(source="ibge", fetched_at=updated_at, warning=None)
            if fetched_at:
                return dict(source="cache", fetched_at=fetched_at,
                            warning=warning or (None if fresh else
                                "Não foi possível atualizar o IBGE; usando o catálogo oficial salvo."))
            raise CatalogUnavailable(failure)

    def search(self, uf: str, query: str, limit: int = 20) -> dict[str, Any]:
        uf = uf.strip().upper()
        if uf not in UF_CODES:
            raise ValueError("UF inválida")
        term = search_text(query)
        if len(term) < 2:
            raise ValueError("Digite pelo menos 2 caracteres para pesquisar o município.")
        info = self.ensure()
        with self.store.connect() as con:
            con.execute("BEGIN")
            info["fetched_at"] = con.execute("SELECT fetched_at FROM ibge_catalog WHERE id=1").fetchone()[0]
            params = [uf, term, term]
            where = "uf=? AND (instr(search_name,?)>0 OR instr(id,?)>0)"
            total = con.execute(f"SELECT count(*) FROM ibge_municipalities WHERE {where}", params).fetchone()[0]
            rows = con.execute(f"SELECT id,name,uf FROM ibge_municipalities WHERE {where} "
                               "ORDER BY search_name,id LIMIT ?", [*params, limit]).fetchall()
        return dict(items=[dict(row) for row in rows], total=total, uf=uf, query=query.strip(), **info)

    def municipality(self, city_id: str) -> dict[str, str]:
        self.ensure()
        with self.store.connect() as con:
            row = con.execute("SELECT id,name,uf FROM ibge_municipalities WHERE id=?", [city_id]).fetchone()
        if row is None:
            raise ValueError("Município não encontrado no catálogo oficial. Atualize a busca e selecione um resultado.")
        return dict(row)
