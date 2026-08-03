"""Small HTTP helper for pricing adapters (stdlib only)."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_UA = os.getenv(
    "BRANDMONITOR_PRICING_UA",
    "BrandMonitorPricingEngine/1.0 (+https://github.com/dayangh-a11y/BrandMonitor)",
)
DEFAULT_TIMEOUT = float(os.getenv("BRANDMONITOR_PRICING_TIMEOUT", "20"))


class HttpError(Exception):
    def __init__(self, message: str, *, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    form_body: dict[str, str] | None = None,
    timeout: float | None = None,
    insecure_tls: bool = False,
) -> tuple[int, Any]:
    """Perform an HTTP request and parse JSON when possible.

    Returns (status_code, parsed_json_or_text).
    Raises HttpError on transport failure.
    """
    data: bytes | None = None
    req_headers = {"User-Agent": DEFAULT_UA, "Accept": "application/json, */*"}
    if headers:
        req_headers.update(headers)

    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    elif form_body is not None:
        data = urllib.parse.urlencode(form_body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    ctx = None
    if insecure_tls:
        ctx = ssl._create_unverified_context()
    else:
        ctx = ssl.create_default_context()

    try:
        with urllib.request.urlopen(
            req, timeout=timeout or DEFAULT_TIMEOUT, context=ctx
        ) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            status = int(resp.status)
    except urllib.error.HTTPError as e:
        raw = e.read() if hasattr(e, "read") else b""
        text = raw.decode("utf-8", errors="replace") if raw else ""
        status = int(e.code)
        # still try to parse body for adapters
        try:
            return status, json.loads(text) if text else None
        except json.JSONDecodeError:
            raise HttpError(
                f"HTTP {status} for {url}", status=status, body=text[:2000]
            ) from e
    except Exception as e:
        raise HttpError(f"{type(e).__name__}: {e}", status=None, body="") from e

    if not text:
        return status, None
    try:
        return status, json.loads(text)
    except json.JSONDecodeError:
        return status, text
