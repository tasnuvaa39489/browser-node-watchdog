from __future__ import annotations

import time
from typing import Any

import requests

from browser_watchdog.config import InstanceConfig

from .base import AdapterError, DiscoveredProfile


class BitBrowserAdapter:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:54345",
        timeout_seconds: float = 30,
        load_extensions: bool = True,
        session: requests.Session | None = None,
        sleeper=time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.load_extensions = load_extensions
        self.session = session or requests.Session()
        self.sleeper = sleeper

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.session.post(
                f"{self.base_url}{path}",
                json=body,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise AdapterError(f"BitBrowser {path} failed: {exc}") from exc
        if not isinstance(payload, dict) or not payload.get("success", False):
            message = payload.get("msg") if isinstance(payload, dict) else "invalid response"
            raise AdapterError(f"BitBrowser {path} failed: {message}")
        data = payload.get("data") or {}
        return data if isinstance(data, dict) else {}

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        if not profile_id:
            raise AdapterError("BitBrowser profile_id is required")
        return self._post("/browser/detail", {"id": profile_id})

    def start(self, profile_id: str) -> dict[str, Any]:
        return self._post(
            "/browser/open",
            {"id": profile_id, "loadExtensions": self.load_extensions, "args": []},
        )

    def stop(self, profile_id: str) -> None:
        self._post("/browser/close", {"id": profile_id})

    def restart(self, instance: InstanceConfig, stop_delay_seconds: int) -> None:
        profile = self.get_profile(instance.profile_id)
        running = int(profile.get("status") or 0) == 1
        if running:
            self.stop(instance.profile_id)
            self.sleeper(stop_delay_seconds)
        self.start(instance.profile_id)

    def discover_profiles(self) -> list[DiscoveredProfile]:
        profiles: list[DiscoveredProfile] = []
        page = 0
        page_size = 100
        while True:
            data = self._post("/browser/list", {"page": page, "pageSize": page_size})
            items = data.get("list") or []
            if not isinstance(items, list):
                raise AdapterError("BitBrowser /browser/list returned invalid list")
            for item in items:
                if not isinstance(item, dict):
                    continue
                profile_id = str(item.get("id") or "").strip()
                if not profile_id:
                    continue
                profiles.append(
                    DiscoveredProfile(
                        browser_type="bitbrowser",
                        profile_id=profile_id,
                        profile_name=str(item.get("name") or "").strip(),
                        running=int(item.get("status") or 0) == 1,
                    )
                )
            if len(items) < page_size:
                break
            page += 1
        return profiles
