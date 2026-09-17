from __future__ import annotations

from typing import Any

import requests


class CentralServiceError(RuntimeError):
    """Raised when ai-compare-server cannot provide a valid response."""


class CentralClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout_seconds: float = 15,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.username = username
        self.password = password
        self._logged_in = False

    def _login(self) -> None:
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/login",
                json={"username": self.username, "password": self.password},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise CentralServiceError(f"panel login failed: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise CentralServiceError("panel login returned an invalid response")
        self._logged_in = True

    def _clear_login(self) -> None:
        self._logged_in = False
        cookies = getattr(self.session, "cookies", None)
        if cookies is not None:
            cookies.clear()

    def _get(self, path: str, *, authenticated: bool):
        if authenticated and not self._logged_in:
            self._login()
        response = self.session.get(
            f"{self.base_url}{path}",
            headers={},
            timeout=self.timeout_seconds,
        )
        if authenticated and response.status_code == 401:
            self._clear_login()
            self._login()
            response = self.session.get(
                f"{self.base_url}{path}",
                headers={},
                timeout=self.timeout_seconds,
            )
        return response

    def _get_json(self, path: str, *, authenticated: bool) -> dict[str, Any]:
        try:
            response = self._get(path, authenticated=authenticated)
            response.raise_for_status()
            payload = response.json()
        except CentralServiceError:
            raise
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
