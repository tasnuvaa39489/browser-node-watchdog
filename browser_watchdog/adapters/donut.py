from __future__ import annotations

import ctypes
import time
from typing import Any

from browser_watchdog.config import InstanceConfig

from .base import AdapterError, DiscoveredProfile


class DonutUiaAdapter:
    """Control Donut profiles through Windows UI Automation."""

    HEADER_TEXTS = (
        "名称",
        "标签",
        "备注",
        "代理 / VPN",
        "扩展",
        "DNS",
        "全选",
        "Name",
        "Tags",
        "Note",
        "Proxy / VPN",
        "EXT",
        "Select all",
    )
    START_ACTION_TEXTS = ("启动", "Launch")
    STOP_ACTION_TEXTS = ("停止", "Stop")
    ACTION_TEXTS = START_ACTION_TEXTS + STOP_ACTION_TEXTS
    SELECT_PROFILE_TEXTS = ("选择配置文件", "Select profile")
    PROFILE_INFO_TEXTS = ("配置文件信息", "Profile info")
    SKIP_AS_NAME = HEADER_TEXTS + (
        "配置文件信息",
        "Profile info",
        "无标签",
        "No tags",
        "无备注",
        "No Note",
        "未选择",
        "选择配置文件",
        "Select profile",
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
        windows = Desktop(backend="win32").windows()
        exact = [window for window in windows if window.window_text() == self.window_title]
        if len(exact) != 1:
            matches = [window.window_text() for window in windows if "Donut" in window.window_text()]
            raise AdapterError(
                f"Donut window must match exactly once: {self.window_title!r}; "
                f"matches={len(exact)} donut_windows={matches}"
            )
        try:
            return Desktop(backend="uia").window(handle=exact[0].handle).wrapper_object()
        except Exception as exc:
            raise AdapterError(f"failed to connect Donut UIA window: {exc}") from exc

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
            if text in self.SELECT_PROFILE_TEXTS:
                if current:
                    profiles.append(current)
                current = {}
            elif text in self.ACTION_TEXTS:
                if current is None:
                    current = {}
                current["action_btn"] = item
                current["is_running"] = text in self.STOP_ACTION_TEXTS
            elif text in self.PROFILE_INFO_TEXTS:
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
