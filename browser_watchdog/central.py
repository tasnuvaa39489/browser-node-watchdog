from __future__ import annotations

from typing import Any

import requests


class CentralServiceError(RuntimeError):
    """Raised when ai-compare-server cannot provide a valid response."""


class CentralClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: float = 15,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def _get_json(self, path: str, *, authenticated: bool) -> dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.base_url}{path}",
                headers=self.headers if authenticated else {},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise CentralServiceError(f"GET {path} failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise CentralServiceError(f"GET {path} returned non-object JSON")
        return payload

    def check_health(self) -> dict[str, Any]:
        payload = self._get_json("/api/health", authenticated=False)
        if payload.get("status") != "running":
            raise CentralServiceError(f"central health is not running: {payload.get('status')!r}")
        return payload

    def get_ai_status(self) -> dict[str, dict[str, Any]]:
        payload = self._get_json("/api/get_ai_status", authenticated=True)
        browsers = payload.get("browsers")
        if not isinstance(browsers, list):
            raise CentralServiceError("/api/get_ai_status missing browsers list")
        result: dict[str, dict[str, Any]] = {}
        for browser in browsers:
            if not isinstance(browser, dict):
                continue
            name = str(browser.get("browserName") or "").strip()
            if name:
                result[name] = browser
        return result
