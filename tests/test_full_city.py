from __future__ import annotations

from pathlib import Path
import sqlite3

import requests

from compras_crawler.client import PageData
from compras_crawler.full_city import FullCityConfig, FullCityCrawler


class FakeAuthResponse:
    status_code = 401


class FakeAuthRetryClient:
    def __init__(self):
        self.calls: list[bool] = []

    def fetch_page(self, path, params, *, use_auth=False):
        self.calls.append(use_auth)
        if not use_auth:
            error = requests.HTTPError("unauthorized")
            error.response = FakeAuthResponse()
            raise error
        return PageData(
            url="https://dadosabertos.compras.gov.br/protected",
            page_number=1,
            params=params,
            records=[],
            raw={"resultado": [], "paginasRestantes": 0},
            content_type="application/json",
            status_code=200,
        )


def test_full_city_config_derives_paths(tmp_path: Path):
    config = FullCityConfig(
        db_path=tmp_path / "floripa",
        start_date="2026-01-01",
        end_date="2026-12-31",
        state_uf="sc",
        municipality_code=4205407,
    )

    assert config.state_uf == "SC"
    assert config.bronze_db_path == tmp_path / "floripa_bronze.duckdb"
    assert config.ops_db_path == tmp_path / "ops" / "floripa_ops.sqlite"


def test_full_city_retries_with_token_only_after_unauthorized(tmp_path: Path):
    config = FullCityConfig(
        db_path=tmp_path / "floripa",
        start_date="2026-01-01",
        end_date="2026-12-31",
        state_uf="SC",
        municipality_code=4205407,
        token="abc",
        delay_seconds=0,
    )
    crawler = FullCityCrawler(config)
    client = FakeAuthRetryClient()
    crawler.client = client

    page, auth_used = crawler._fetch_page("protected", "/protected", {})

    assert page is not None
    assert auth_used is True
    assert client.calls == [False, True]


def test_ocds_bad_request_keeps_bounded_sanitized_diagnostic_without_checkpoint(tmp_path, monkeypatch):
    config = FullCityConfig(db_path=tmp_path / "brusque", token="configured-secret")
    crawler = FullCityCrawler(config)
    crawler.warehouse.init_schema()
    crawler.crawl_state.init_schema()
    crawler.ops_store.init_schema()
    resp = requests.Response()
    resp.status_code = 400
    resp.encoding = "utf-8"
    resp._content = (
        b'{"message":"Intervalo invalido. Authorization: Bearer echoed-secret configured-secret '
        + b"x" * 900 + b'","password":"other-secret"}'
    )

    def fail(*args, **kwargs):
        raise requests.HTTPError("bad request", response=resp)

    monkeypatch.setattr(crawler.client, "fetch_page", fail)
    crawler._crawl_ocds(["83102343000194"])
    assert len(crawler.errors) == 1
    message = crawler.errors[0]["message"]
    assert "HTTP 400" in message and "Intervalo invalido" in message
    assert not any(secret in message for secret in ("echoed-secret", "configured-secret", "other-secret"))
    assert len(message) < 640
    with sqlite3.connect(config.ops_db_path) as con:
        assert con.execute("SELECT count(*) FROM ops_checkpoints").fetchone() == (0,)
