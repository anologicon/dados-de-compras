from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest
import requests

from compras_crawler.web.municipalities import CatalogUnavailable, IBGE_URL, MunicipalityCatalog
from compras_crawler.web.store import AppStore, stamp

PAYLOAD = [
    {"id": 4202909, "nome": "Brusque"},
    {"id": 4205407, "nome": "Florianópolis"},
    {"id": 4216602, "nome": "São José"},
    {"id": 3549904, "nome": "São José dos Campos"},
    {"id": 4202538, "nome": "Bom Jesus"},
    {"id": 4302303, "nome": "Bom Jesus"},
    {"id": 5101837, "nome": "Boa Esperança do Norte", "microrregiao": None},
]


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    store = AppStore(tmp_path)
    store.init_schema()
    catalog = MunicipalityCatalog(store)
    catalog.init_schema()
    monkeypatch.setattr(catalog, "_download", lambda: PAYLOAD)
    return catalog


def seed(catalog):
    catalog._replace(catalog._parse(PAYLOAD))


def expire(catalog):
    with catalog.store.connect() as con:
        con.execute("UPDATE ibge_catalog SET fetched_at=?", [stamp(datetime.now(timezone.utc) - timedelta(days=31))])


def offline():
    raise requests.Timeout("simulated unavailable IBGE")


def test_search_uses_official_names_without_accents_or_case(catalog):
    result = catalog.search("sc", "fLoRiAnOpOlIs")
    assert result["items"] == [{"id": "4205407", "name": "Florianópolis", "uf": "SC"}]
    assert result["source"] == "ibge"
    assert result["fetched_at"]
    assert catalog.search("SC", "4216602")["items"][0]["name"] == "São José"
    assert catalog.search("MT", "boa esperanca")["items"][0]["id"] == "5101837"


def test_state_filters_disambiguate_homonyms_and_results_are_limited(catalog):
    assert catalog.search("SC", "bom jesus")["items"][0]["id"] == "4202538"
    assert catalog.search("RS", "bom jesus")["items"][0]["id"] == "4302303"
    result = catalog.search("SC", "42", limit=1)
    assert len(result["items"]) == 1 and result["total"] == 4
    assert catalog.search("SC", "sao jose")["total"] == 1


def test_cache_survives_restart_without_network(catalog, monkeypatch):
    seed(catalog)
    second = MunicipalityCatalog(catalog.store)
    monkeypatch.setattr(second, "_download", offline)
    result = second.search("SC", "brusque")
    assert result["source"] == "cache" and result["warning"] is None
    assert result["items"][0]["id"] == "4202909"


def test_offline_expired_cache_remains_usable(catalog, monkeypatch):
    seed(catalog)
    expire(catalog)
    monkeypatch.setattr(catalog, "_download", offline)
    result = catalog.search("SC", "brusque")
    assert result["source"] == "cache" and "salvo" in result["warning"]
    assert result["items"][0]["id"] == "4202909"
    assert catalog.municipality("4202909")["name"] == "Brusque"


def test_offline_without_cache_is_explicit_and_does_not_hammer_api(catalog, monkeypatch):
    attempts = []
    def fail():
        attempts.append(1)
        offline()
    monkeypatch.setattr(catalog, "_download", fail)
    for _ in range(3):
        with pytest.raises(CatalogUnavailable, match="sem catálogo oficial"):
            catalog.search("SC", "brusque")
    assert len(attempts) == 1


@pytest.mark.parametrize("payload", [None, {}, [], [{"id": 4202909}],
    [{"id": 9900000, "nome": "Inválido"}], [PAYLOAD[0], PAYLOAD[0]]])
def test_invalid_response_never_replaces_last_good_catalog(catalog, monkeypatch, payload):
    seed(catalog)
    expire(catalog)
    monkeypatch.setattr(catalog, "_download", lambda: payload)
    result = catalog.search("SC", "brusque")
    assert result["warning"] and result["items"][0]["id"] == "4202909"
    with catalog.store.connect() as con:
        assert con.execute("SELECT count(*) FROM ibge_municipalities").fetchone()[0] == len(PAYLOAD)


def test_failed_refresh_write_preserves_usable_cache(catalog, monkeypatch):
    seed(catalog)
    expire(catalog)
    def full_disk(rows):
        raise sqlite3.OperationalError("database or disk is full")
    monkeypatch.setattr(catalog, "_replace", full_disk)
    result = catalog.search("SC", "brusque")
    assert result["source"] == "cache"
    assert "salvar" in result["warning"]
    assert result["items"][0]["id"] == "4202909"


def test_failed_cache_write_rolls_back_previous_snapshot(catalog):
    seed(catalog)
    rows = catalog._parse(PAYLOAD)
    with pytest.raises(sqlite3.IntegrityError):
        catalog._replace([rows[0], rows[0]])
    assert catalog.search("SC", "florianopolis")["total"] == 1


def test_unknown_code_or_invalid_search_is_not_accepted(catalog):
    with pytest.raises(ValueError, match="não encontrado"):
        catalog.municipality("4200000")
    with pytest.raises(ValueError, match="UF inválida"):
        catalog.search("ZZ", "brusque")
    with pytest.raises(ValueError, match="2 caracteres"):
        catalog.search("SC", "  ")


def test_concurrent_first_search_downloads_once(catalog, monkeypatch):
    calls = []
    def download():
        calls.append(1)
        return PAYLOAD
    monkeypatch.setattr(catalog, "_download", download)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: catalog.search("SC", "brusque"), range(4)))
    assert len(calls) == 1
    assert {r["items"][0]["id"] for r in results} == {"4202909"}


def test_download_uses_fixed_url_without_authentication_or_redirects(catalog, monkeypatch):
    calls = []
    response = requests.Response()
    response.status_code = 302
    response.headers["Location"] = "https://attacker.example"
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(ValueError):
        MunicipalityCatalog._download(catalog)
    assert calls == [(IBGE_URL, {"timeout": (5, 15), "allow_redirects": False})]
