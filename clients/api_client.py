"""Reusable, deterministic HTTP client for API-test execution."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from requests.auth import AuthBase

from config.settings import Settings

SENSITIVE_KEYS = frozenset({
    "authorization", "api_key", "apikey", "access_token", "bearer", "password",
    "secret", "token", "x_api_key",
})
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)\b(password|secret|token|api[_-]?key|access[_-]?token)\b\s*([:=])\s*([^\s,;]+)"
)
AUTHORIZATION_TEXT_PATTERN = re.compile(r"(?i)(authorization\s*[:=]\s*)([^\r\n]+)")
BEARER_TEXT_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;]+")


class APIClientError(RuntimeError):
    """An HTTP transport failure with request context."""


def mask_sensitive(value: Any, key: str | None = None) -> Any:
    """Return a recursively sanitized copy suitable for logs and reports."""
    if key and key.lower().replace("-", "_") in SENSITIVE_KEYS:
        return "***MASKED***"
    if isinstance(value, Mapping):
        return {str(item_key): mask_sensitive(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_sensitive(item) for item in value)
    return value


def mask_sensitive_text(text: str) -> str:
    """Mask common credential formats when an external log line must be retained."""
    masked = AUTHORIZATION_TEXT_PATTERN.sub(r"\1***MASKED***", text)
    masked = SENSITIVE_TEXT_PATTERN.sub(r"\1\2***MASKED***", masked)
    return BEARER_TEXT_PATTERN.sub("Bearer ***MASKED***", masked)


@dataclass(frozen=True, slots=True)
class APIResponse:
    """Captured response data detached from the requests implementation."""

    status_code: int
    headers: dict[str, str]
    text: str
    json_body: Any | None
    duration_ms: float
    url: str


class APIClient:
    """HTTP client that only performs declared API requests; it executes no generated code."""

    def __init__(
        self,
        settings: Settings,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if not settings.api_base_url:
            raise ValueError("API_BASE_URL must be configured before creating an API client.")
        settings.assert_execution_allowed()
        self._settings = settings
        self._session = session or requests.Session()
        self._logger = logger or logging.getLogger(__name__)

    def get(self, path: str, **kwargs: Any) -> APIResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> APIResponse:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> APIResponse:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> APIResponse:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> APIResponse:
        return self.request("DELETE", path, **kwargs)

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        query_params: Mapping[str, Any] | None = None,
        path_params: Mapping[str, Any] | None = None,
        json_body: Any | None = None,
        auth: AuthBase | tuple[str, str] | None = None,
        timeout: float | None = None,
    ) -> APIResponse:
        """Send a request and capture the response. Network failures raise APIClientError."""
        resolved_path = path.format(**(path_params or {}))
        url = urljoin(f"{self._settings.api_base_url}/", resolved_path.lstrip("/"))
        merged_headers = {"Accept": "application/json", **(headers or {})}
        if self._settings.api_bearer_token and "Authorization" not in merged_headers:
            merged_headers["Authorization"] = f"Bearer {self._settings.api_bearer_token}"
        resolved_auth = auth
        if resolved_auth is None and self._settings.api_username and self._settings.api_password:
            resolved_auth = (self._settings.api_username, self._settings.api_password)

        self._logger.info(
            "API request method=%s url=%s params=%s headers=%s body=%s",
            method.upper(), url, mask_sensitive(query_params or {}),
            mask_sensitive(merged_headers), mask_sensitive(json_body),
        )
        started = time.perf_counter()
        try:
            response = self._session.request(
                method=method.upper(), url=url, headers=merged_headers, params=query_params,
                json=json_body, auth=resolved_auth, timeout=timeout or self._settings.api_timeout,
            )
        except requests.RequestException as exc:
            raise APIClientError(f"{method.upper()} {url} failed: {exc}") from exc
        duration_ms = (time.perf_counter() - started) * 1000
        try:
            json_body_response: Any | None = response.json()
        except ValueError:
            json_body_response = None
        captured = APIResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            text=response.text,
            json_body=json_body_response,
            duration_ms=duration_ms,
            url=response.url,
        )
        self._logger.info(
            "API response method=%s url=%s status=%s duration_ms=%.2f headers=%s body=%s",
            method.upper(), captured.url, captured.status_code, captured.duration_ms,
            mask_sensitive(captured.headers), mask_sensitive(captured.json_body),
        )
        return captured
