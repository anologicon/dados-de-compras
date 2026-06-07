from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
import csv
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from .normalize import extract_records

DEFAULT_BASE_HOST = "dadosabertos.compras.gov.br"


@dataclass(frozen=True)
class PageData:
    url: str
    page_number: int
    params: dict[str, Any]
    records: list[dict[str, Any]]
    raw: Any
    content_type: str
    status_code: int


def validate_base_url(base_url: str, *, token: str | None = None) -> None:
    parsed = urlparse(base_url)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()

    if scheme != "https":
        raise ValueError("base_url must use https://")
    if not parsed.netloc or not hostname:
        raise ValueError("base_url must include a host")
    if parsed.username or parsed.password:
        raise ValueError("base_url must not include credentials")
    if parsed.fragment:
        raise ValueError("base_url must not include a fragment")
    if parsed.query:
        raise ValueError("base_url must not include a query string")
    if token and hostname != DEFAULT_BASE_HOST:
        raise ValueError(f"tokened runs are only allowed against https://{DEFAULT_BASE_HOST}")
    if token and parsed.port not in (None, 443):
        raise ValueError("tokened runs must use the default https port")


class ComprasClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ):
        validate_base_url(base_url, token=token)
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session = session or requests.Session()

    def _headers(self, accept: str = "json") -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if accept == "csv":
            headers["Accept"] = "text/csv"
        else:
            headers["Accept"] = "application/json"
        return headers

    def fetch_page(
        self,
        path: str,
        params: dict[str, Any],
        *,
        accept: str = "json",
    ) -> PageData:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        response = self.session.get(url, params=params, headers=self._headers(accept), timeout=self.timeout)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if accept == "csv" or "csv" in content_type:
            raw: Any = response.text
            records = self._parse_csv(response.text)
        else:
            raw = response.json()
            records = extract_records(raw)
        return PageData(
            url=url,
            page_number=int(params.get("pagina", 1)),
            params=dict(params),
            records=records,
            raw=raw,
            content_type=content_type,
            status_code=response.status_code,
        )

    def iter_pages(
        self,
        path: str,
        params: dict[str, Any],
        *,
        accept: str = "json",
        job_name: str | None = None,
    ):
        page = int(params.get("pagina", 1) or 1)
        base_params = dict(params)
        while True:
            request_params = dict(base_params)
            request_params["pagina"] = page
            page_data = self.fetch_page(path, request_params, accept=accept)
            yield page_data
            if accept == "csv":
                if not page_data.records:
                    break
                page += 1
                continue
            if isinstance(page_data.raw, dict) and int(page_data.raw.get("paginasRestantes", 0) or 0) <= 0:
                break
            if not page_data.records:
                break
            page += 1

    def _parse_csv(self, text: str) -> list[dict[str, Any]]:
        if not text.strip():
            return []
        reader = csv.DictReader(StringIO(text))
        return [dict(row) for row in reader]
