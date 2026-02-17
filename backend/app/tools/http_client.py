"""HTTP JSON helper with retries and normalized error taxonomy."""

from __future__ import annotations

import json
import logging
import socket
import time
from time import perf_counter
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


LOGGER = logging.getLogger("finance_research_agent.tools.http")


class ToolHttpError(RuntimeError):
    """Raised when an HTTP request cannot be completed successfully."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retriable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retriable = retriable


class HttpJsonClient:
    """Performs JSON HTTP requests with retries for transient failures."""

    _RETRYABLE_STATUS_CODES: tuple[int, ...] = (429, 500, 502, 503, 504)

    def __init__(
        self,
        timeout_seconds: float = 20.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Perform HTTP GET and decode JSON payload."""
        query = urlencode(params or {}, doseq=True)
        target = f"{url}?{query}" if query else url
        request = Request(target, headers=headers or {}, method="GET")
        return self._request_json(request)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any] | list[Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Perform HTTP POST with a JSON body and decode JSON payload."""
        body = json.dumps(payload).encode("utf-8")
        merged_headers = {"Content-Type": "application/json"}
        if headers:
            merged_headers.update(headers)
        request = Request(url, data=body, headers=merged_headers, method="POST")
        return self._request_json(request)

    def _request_json(self, request: Request) -> dict[str, Any] | list[Any]:
        attempt = 0
        request_label = _sanitize_url(request.full_url)
        method = str(request.get_method() or "GET")
        while True:
            started = perf_counter()
            LOGGER.info(
                "http_request_start method=%s url=%s attempt=%s timeout=%.1f",
                method,
                request_label,
                attempt + 1,
                self._timeout_seconds,
            )
            try:
                with urlopen(request, timeout=self._timeout_seconds) as response:
                    raw_payload = response.read()
                    status_code = int(response.getcode() or 0)
            except HTTPError as exc:
                status_code = int(exc.code)
                retriable = status_code in self._RETRYABLE_STATUS_CODES
                elapsed_ms = (perf_counter() - started) * 1000.0
                if retriable and attempt < self._max_retries:
                    LOGGER.warning(
                        "http_request_retry method=%s url=%s status=%s elapsed_ms=%.2f attempt=%s",
                        method,
                        request_label,
                        status_code,
                        elapsed_ms,
                        attempt + 1,
                    )
                    self._sleep_before_retry(attempt)
                    attempt += 1
                    continue
                detail = self._safe_error_body(exc)
                LOGGER.error(
                    "http_request_failed method=%s url=%s status=%s retriable=%s elapsed_ms=%.2f",
                    method,
                    request_label,
                    status_code,
                    retriable,
                    elapsed_ms,
                )
                raise ToolHttpError(
                    f"HTTP {status_code} for {request.full_url}. {detail}",
                    status_code=status_code,
                    retriable=retriable,
                ) from exc
            except (URLError, TimeoutError, socket.timeout) as exc:
                elapsed_ms = (perf_counter() - started) * 1000.0
                if attempt < self._max_retries:
                    LOGGER.warning(
                        "http_request_retry method=%s url=%s reason=%s elapsed_ms=%.2f attempt=%s",
                        method,
                        request_label,
                        exc.__class__.__name__,
                        elapsed_ms,
                        attempt + 1,
                    )
                    self._sleep_before_retry(attempt)
                    attempt += 1
                    continue
                LOGGER.error(
                    "http_request_failed method=%s url=%s reason=%s retriable=true elapsed_ms=%.2f",
                    method,
                    request_label,
                    exc.__class__.__name__,
                    elapsed_ms,
                )
                raise ToolHttpError(
                    f"Network failure for {request.full_url}: {exc}",
                    retriable=True,
                ) from exc

            try:
                payload = json.loads(raw_payload.decode("utf-8"))
            except json.JSONDecodeError as exc:
                elapsed_ms = (perf_counter() - started) * 1000.0
                LOGGER.error(
                    "http_request_failed method=%s url=%s reason=invalid_json status=%s elapsed_ms=%.2f",
                    method,
                    request_label,
                    status_code,
                    elapsed_ms,
                )
                raise ToolHttpError(
                    f"Invalid JSON response from {request.full_url}.",
                    retriable=False,
                ) from exc
            elapsed_ms = (perf_counter() - started) * 1000.0
            LOGGER.info(
                "http_request_end method=%s url=%s status=%s elapsed_ms=%.2f",
                method,
                request_label,
                status_code,
                elapsed_ms,
            )
            return payload

    def _sleep_before_retry(self, attempt: int) -> None:
        # Simple exponential backoff with deterministic timing.
        delay = self._retry_backoff_seconds * (2**attempt)
        time.sleep(delay)

    def _safe_error_body(self, exc: HTTPError) -> str:
        try:
            body = exc.read().decode("utf-8")
        except Exception:  # pragma: no cover - defensive fallback
            return ""
        text = body.strip()
        if not text:
            return ""
        if len(text) > 240:
            return text[:240] + "..."
        return text


def _sanitize_url(raw_url: str) -> str:
    try:
        parsed = urlsplit(raw_url)
    except Exception:
        return raw_url
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    redacted = []
    sensitive_keys = {
        "api_key",
        "apikey",
        "key",
        "token",
        "access_token",
        "authorization",
    }
    for key, value in query_pairs:
        if key.lower() in sensitive_keys:
            redacted.append((key, "***"))
        else:
            redacted.append((key, value))
    safe_query = urlencode(redacted, doseq=True)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, ""))
