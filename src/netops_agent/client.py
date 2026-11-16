"""Thin Meraki Dashboard API v1 client: auth, 429 retry, pagination, call counting."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.meraki.com/api/v1"


class MerakiError(RuntimeError):
    pass


class MerakiClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("MERAKI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("MERAKI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.max_retries = max_retries
        self.sleep = sleep
        self.calls = 0  # HTTP requests sent, including retries
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=30.0,
            transport=transport,
            follow_redirects=True,
        )

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET a path; follow Link rel=next pages for list responses."""
        url: str | None = path
        result: Any = None
        while url:
            resp = self._send(url, params)
            params = None  # the next link already carries the query
            data = resp.json()
            if isinstance(data, list):
                result = (result or []) + data
                nxt = resp.links.get("next", {}).get("url")
                url = nxt
            else:
                return data
        return result

    def _send(self, url: str, params: dict[str, Any] | None) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            self.calls += 1
            resp = self._http.get(url, params=params)
            if resp.status_code == 429:
                if attempt == self.max_retries:
                    break
                self.sleep(float(resp.headers.get("Retry-After", 2**attempt)))
                continue
            if resp.status_code >= 400:
                raise MerakiError(f"GET {url} -> {resp.status_code}: {resp.text[:200]}")
            return resp
        raise MerakiError(f"GET {url}: still rate limited after {self.max_retries} retries")


def fixture_name(request: httpx.Request, base_path: str) -> str:
    path = request.url.path.removeprefix(base_path).strip("/")
    name = path.replace("/", "_")
    if pt := request.url.params.get("productType"):
        name += f"_{pt}"
    return name


class FixtureTransport(httpx.BaseTransport):
    """Serve saved API responses from a directory (offline tests and eval)."""

    def __init__(self, directory: str | Path, base_url: str = DEFAULT_BASE_URL) -> None:
        self.dir = Path(directory)
        self.base_path = httpx.URL(base_url).path

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        f = self.dir / f"{fixture_name(request, self.base_path)}.json"
        if not f.exists():
            return httpx.Response(404, json={"errors": [f"no fixture {f.name}"]})
        return httpx.Response(200, json=json.loads(f.read_text()))
