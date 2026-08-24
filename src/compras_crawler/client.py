from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from io import StringIO
from time import sleep
import csv
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from .normalize import extract_records

DEFAULT_BASE_HOST = "dadosabertos.compras.gov.br"
DEFAULT_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


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
        max_retries: int = 5,
        retry_backoff_seconds: float = 2.0,
    ):
        validate_base_url(base_url, token=token)
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

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
        response = self._get_with_retries(url, params=params, accept=accept)
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

    def _get_with_retries(self, url: str, *, params: dict[str, Any], accept: str) -> requests.Response:
        last_error: requests.RequestException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, headers=self._headers(accept), timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                self._sleep_before_retry(attempt=attempt, response=None)
                continue
            if response.status_code not in DEFAULT_RETRY_STATUS_CODES or attempt >= self.max_retries:
                return response
            self._sleep_before_retry(attempt=attempt, response=response)
        if last_error is not None:
            raise last_error
        raise RuntimeError("request retry loop exited unexpectedly")

    def _sleep_before_retry(self, *, attempt: int, response: requests.Response | None) -> None:
        retry_after = _retry_after_seconds(response.headers.get("Retry-After")) if response is not None else None
        if retry_after is None:
            retry_after = min(60.0, self.retry_backoff_seconds * (2**attempt))
        if retry_after > 0:
            sleep(retry_after)

    def _parse_csv(self, text: str) -> list[dict[str, Any]]:
        if not text.strip():
            return []
        reader = csv.DictReader(StringIO(text))
        return [dict(row) for row in reader]


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - datetime.now(tz=timezone.utc)).total_seconds())
