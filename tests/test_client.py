from __future__ import annotations

from dataclasses import dataclass

import pytest

from compras_crawler.client import ComprasClient


@dataclass
class FakeResponse:
    json_data: object | None = None
    text_data: str = ""
    status_code: int = 200
    content_type: str = "application/json"

    def json(self):
        if self.json_data is None:
            raise ValueError("no json payload")
        return self.json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    @property
    def text(self):
        return self.text_data

    @property
    def headers(self):
        return {"content-type": self.content_type}


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return self.responses.pop(0)


def test_iter_pages_json_uses_pagination_and_token():
    session = FakeSession(
        [
            FakeResponse(json_data={"resultado": [{"codigoUasg": "1"}], "paginasRestantes": 1}),
            FakeResponse(json_data={"resultado": [{"codigoUasg": "2"}], "paginasRestantes": 0}),
        ]
    )
    client = ComprasClient("https://dadosabertos.compras.gov.br", token="abc", session=session)

    pages = list(client.iter_pages("/modulo-uasg/1_consultarUasg", {"statusUasg": True}))

    assert [page.page_number for page in pages] == [1, 2]
    assert pages[0].records == [{"codigoUasg": "1"}]
    assert session.calls[0]["headers"]["Authorization"] == "Bearer abc"
    assert session.calls[0]["params"]["pagina"] == 1
    assert session.calls[1]["params"]["pagina"] == 2


def test_fetch_page_parses_csv():
    session = FakeSession([FakeResponse(text_data="codigoUasg,nomeUasg\n1,A\n2,B\n", content_type="text/csv")])
    client = ComprasClient("https://dadosabertos.compras.gov.br", session=session)

    page = client.fetch_page("/modulo-uasg/1.1_consultarUasg_CSV", {"statusUasg": True}, accept="csv")

    assert page.content_type == "text/csv"
    assert page.records == [
        {"codigoUasg": "1", "nomeUasg": "A"},
        {"codigoUasg": "2", "nomeUasg": "B"},
    ]


def test_client_allows_https_custom_host_without_token():
    session = FakeSession([FakeResponse(json_data={"resultado": []})])
    client = ComprasClient("https://example.com", session=session)

    page = client.fetch_page("/path", {"pagina": 1})

    assert page.url == "https://example.com/path"


def test_client_rejects_http_base_url():
    with pytest.raises(ValueError, match="https://"):
        ComprasClient("http://dadosabertos.compras.gov.br")


def test_client_rejects_tokened_custom_host():
    with pytest.raises(ValueError, match="tokened runs are only allowed"):
        ComprasClient("https://example.com", token="abc")
