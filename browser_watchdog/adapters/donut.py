from __future__ import annotations

import ctypes
import time
from typing import Any

import requests

from browser_watchdog.config import InstanceConfig

from .base import AdapterError, DiscoveredProfile


class DonutRestAdapter:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: float = 30,
        session: requests.Session | None = None,
        sleeper=time.sleep,
    ) -> None:
        if not token:
            raise AdapterError("Donut REST API token is required")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.headers = {"Authorization": f"Bearer {token}"}
        self.sleeper = sleeper

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers=self.headers,
                json=body,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise AdapterError(f"Donut {method} {path} failed: {exc}") from exc

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/v1/profiles/{profile_id}")
        profile = payload.get("profile") if isinstance(payload, dict) else None
        if not isinstance(profile, dict):
            raise AdapterError("Donut profile response is invalid")
        return profile

    def restart(self, instance: InstanceConfig, stop_delay_seconds: int) -> None:
        if not instance.profile_id:
            raise AdapterError(f"{instance.browser_name}: Donut REST mode requires profile_id")
        profile = self.get_profile(instance.profile_id)
        if bool(profile.get("is_running")):
            self._request("POST", f"/v1/profiles/{instance.profile_id}/kill")
            self.sleeper(stop_delay_seconds)
        self._request(
            "POST",
            f"/v1/profiles/{instance.profile_id}/run",
            {"headless": False},
        )

    def discover_profiles(self) -> list[DiscoveredProfile]:
        payload = self._request("GET", "/v1/profiles")
        items = payload.get("profiles") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise AdapterError("Donut /v1/profiles returned invalid profiles list")
        profiles: list[DiscoveredProfile] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            profile_id = str(item.get("id") or "").strip()
            if not profile_id:
                continue
            profiles.append(
                DiscoveredProfile(
                    browser_type="donut",
                    profile_id=profile_id,
                    profile_name=str(item.get("name") or "").strip(),
                    running=bool(item.get("is_running")),
                )
            )
        return profiles


class DonutUiaAdapter:
    """UI Automation fallback for Donut installations without REST control."""

    HEADER_TEXTS = ("名称", "标签", "代理 / VPN", "全选")
    ACTION_TEXTS = ("启动", "停止")
    SKIP_AS_NAME = HEADER_TEXTS + (
        "配置文件信息",
        "无标签",
        "未选择",
        "选择配置文件",
    ) + ACTION_TEXTS + ("",)

    def __init__(self, window_title: str = "Donut Browser", sleeper=time.sleep) -> None:
        self.window_title = window_title
        self.sleeper = sleeper

    @staticmethod
    def _desktop_and_uia():
        try:
            from pywinauto import Desktop, uia_defines
        except ImportError as exc:
            raise AdapterError("pywinauto is required for Donut UIA mode") from exc
        return Desktop, uia_defines

    def _get_window(self):
        Desktop, _ = self._desktop_and_uia()
        windows = Desktop(backend="uia").windows()
        exact = [window for window in windows if window.window_text() == self.window_title]
        if exact:
            return exact[0]
        partial = [window for window in windows if self.window_title in window.window_text()]
        if partial:
            return partial[0]
        raise AdapterError(f"Donut window not found: {self.window_title}")

    def _activate_window(self) -> None:
        window = self._get_window()
        user32 = ctypes.windll.user32
        user32.ShowWindow(window.handle, 9)
        user32.SetForegroundWindow(window.handle)
        try:
            window.set_focus()
        except Exception:
            pass
        self.sleeper(0.3)

    def _parse_profiles(self) -> list[dict[str, Any]]:
        window = self._get_window()
        profiles: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for item in window.descendants(control_type="DataItem"):
            text = item.window_text() or item.element_info.name
            if text in self.HEADER_TEXTS:
                continue
            if text == "选择配置文件":
                if current:
                    profiles.append(current)
                current = {}
            elif text in self.ACTION_TEXTS:
                if current is None:
                    current = {}
                current["action_btn"] = item
                current["is_running"] = text == "停止"
            elif text == "配置文件信息":
                if current:
                    profiles.append(current)
                    current = None
            elif current is not None and "name" not in current and text not in self.SKIP_AS_NAME:
                current["name"] = text
        if current:
            profiles.append(current)
        return profiles

    def _find_profile(self, profile_name: str) -> dict[str, Any]:
        matches = [item for item in self._parse_profiles() if item.get("name") == profile_name]
        if len(matches) != 1:
            names = [item.get("name") for item in self._parse_profiles()]
            raise AdapterError(
                f"Donut profile must match exactly once: {profile_name!r}; matches={len(matches)} names={names}"
            )
        return matches[0]

    def _trigger(self, button) -> None:
        _, uia_defines = self._desktop_and_uia()
        try:
            legacy = uia_defines.get_elem_interface(button.element_info.element, "LegacyIAccessible")
            legacy.DoDefaultAction()
            return
        except Exception:
            self._activate_window()
        try:
            if "双击" in button.legacy_properties().get("DefaultAction", ""):
                button.double_click_input()
            else:
                button.click_input()
        except Exception as exc:
            raise AdapterError(f"Donut UIA action failed: {exc}") from exc

    def _wait_running(self, profile_name: str, expected: bool, timeout_seconds: int = 30) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            profile = self._find_profile(profile_name)
            if bool(profile.get("is_running")) == expected:
                return
            self.sleeper(1)
        raise AdapterError(f"Donut profile {profile_name!r} did not reach running={expected}")

    def restart(self, instance: InstanceConfig, stop_delay_seconds: int) -> None:
        name = instance.profile_name.strip()
        if not name:
            raise AdapterError(f"{instance.browser_name}: Donut UIA mode requires profile_name")
        profile = self._find_profile(name)
        if bool(profile.get("is_running")):
            button = profile.get("action_btn")
            if button is None:
                raise AdapterError(f"Donut profile {name!r} has no stop button")
            self._trigger(button)
            self._wait_running(name, False)
            self.sleeper(stop_delay_seconds)
        profile = self._find_profile(name)
        button = profile.get("action_btn")
        if button is None:
            raise AdapterError(f"Donut profile {name!r} has no start button")
        self._trigger(button)
        self._wait_running(name, True)

    def discover_profiles(self) -> list[DiscoveredProfile]:
        return [
            DiscoveredProfile(
                browser_type="donut",
                profile_id="",
                profile_name=str(item.get("name") or ""),
                running=bool(item.get("is_running")),
            )
            for item in self._parse_profiles()
            if item.get("name")
        ]
