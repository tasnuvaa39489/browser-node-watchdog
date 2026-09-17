from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when watchdog configuration is invalid."""


@dataclass(frozen=True)
class CentralConfig:
    base_url: str
    username_env: str = "AI_COMPARE_PANEL_USERNAME"
    password_env: str = "AI_COMPARE_PANEL_PASSWORD"
    request_timeout_seconds: float = 15.0


@dataclass(frozen=True)
class WatchdogConfig:
    poll_seconds: int = 300
    stale_minutes: int = 30
    verify_wait_seconds: int = 120
    restart_cooldown_minutes: int = 60
    max_restarts_per_cycle: int = 1
    max_cpu_percent: float = 90.0
    max_memory_percent: float = 90.0
    min_available_memory_mb: int = 2048
    browser_stop_delay_seconds: int = 8


@dataclass(frozen=True)
class BitBrowserConfig:
    enabled: bool = True
    base_url: str = "http://127.0.0.1:54345"
    request_timeout_seconds: float = 30.0
    load_extensions: bool = True


@dataclass(frozen=True)
class DonutConfig:
    enabled: bool = False
    window_title: str = "Donut Browser"


@dataclass(frozen=True)
class BrowserConfigs:
    bitbrowser: BitBrowserConfig = field(default_factory=BitBrowserConfig)
    donut: DonutConfig = field(default_factory=DonutConfig)


@dataclass(frozen=True)
class InstanceConfig:
    browser_name: str
    browser_type: str
    profile_id: str = ""
    profile_name: str = ""
    auto_restart: bool = True
    priority: int = 100


@dataclass(frozen=True)
class AppConfig:
    central: CentralConfig
    watchdog: WatchdogConfig
    browsers: BrowserConfigs
    instances: tuple[InstanceConfig, ...]


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a mapping")
    return value


def _positive_int(value: Any, name: str, default: int) -> int:
    number = int(default if value is None else value)
    if number <= 0:
        raise ConfigError(f"{name} must be > 0")
    return number


def load_raw_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")
    return raw


def load_config(path: str | Path) -> AppConfig:
    raw = load_raw_config(path)
    central_raw = _mapping(raw.get("central"), "central")
    base_url = str(central_raw.get("base_url") or "").strip().rstrip("/")
    if not base_url:
        raise ConfigError("central.base_url is required")
    central = CentralConfig(
        base_url=base_url,
        username_env=str(
            central_raw.get("username_env") or "AI_COMPARE_PANEL_USERNAME"
        ).strip(),
        password_env=str(
            central_raw.get("password_env") or "AI_COMPARE_PANEL_PASSWORD"
        ).strip(),
        request_timeout_seconds=float(central_raw.get("request_timeout_seconds", 15)),
    )

    watchdog_raw = _mapping(raw.get("watchdog"), "watchdog")
    watchdog = WatchdogConfig(
        poll_seconds=_positive_int(watchdog_raw.get("poll_seconds"), "watchdog.poll_seconds", 300),
        stale_minutes=_positive_int(watchdog_raw.get("stale_minutes"), "watchdog.stale_minutes", 30),
        verify_wait_seconds=_positive_int(
            watchdog_raw.get("verify_wait_seconds"), "watchdog.verify_wait_seconds", 120
        ),
        restart_cooldown_minutes=_positive_int(
            watchdog_raw.get("restart_cooldown_minutes"), "watchdog.restart_cooldown_minutes", 60
        ),
        max_restarts_per_cycle=_positive_int(
            watchdog_raw.get("max_restarts_per_cycle"), "watchdog.max_restarts_per_cycle", 1
        ),
        max_cpu_percent=float(watchdog_raw.get("max_cpu_percent", 90)),
        max_memory_percent=float(watchdog_raw.get("max_memory_percent", 90)),
        min_available_memory_mb=_positive_int(
            watchdog_raw.get("min_available_memory_mb"), "watchdog.min_available_memory_mb", 2048
        ),
        browser_stop_delay_seconds=_positive_int(
            watchdog_raw.get("browser_stop_delay_seconds"),
            "watchdog.browser_stop_delay_seconds",
            8,
        ),
    )

    browsers_raw = _mapping(raw.get("browsers"), "browsers")
    bit_raw = _mapping(browsers_raw.get("bitbrowser"), "browsers.bitbrowser")
    donut_raw = _mapping(browsers_raw.get("donut"), "browsers.donut")
    bitbrowser = BitBrowserConfig(
        enabled=bool(bit_raw.get("enabled", True)),
        base_url=str(bit_raw.get("base_url") or "http://127.0.0.1:54345").rstrip("/"),
        request_timeout_seconds=float(bit_raw.get("request_timeout_seconds", 30)),
        load_extensions=bool(bit_raw.get("load_extensions", True)),
    )
    donut = DonutConfig(
        enabled=bool(donut_raw.get("enabled", False)),
        window_title=str(donut_raw.get("window_title") or "Donut Browser"),
    )

    instances_raw = raw.get("instances") or []
    if not isinstance(instances_raw, list):
        raise ConfigError("instances must be a list")
    instances: list[InstanceConfig] = []
    seen_names: set[str] = set()
    for index, item in enumerate(instances_raw):
        data = _mapping(item, f"instances[{index}]")
        browser_name = str(data.get("browser_name") or "").strip()
        browser_type = str(data.get("browser_type") or "").strip().lower()
        if not browser_name:
            raise ConfigError(f"instances[{index}].browser_name is required")
        if browser_name in seen_names:
            raise ConfigError(f"duplicate browser_name: {browser_name}")
        seen_names.add(browser_name)
        if browser_type in {"bit", "bit_browser"}:
            browser_type = "bitbrowser"
        if browser_type not in {"bitbrowser", "donut"}:
            raise ConfigError(f"unsupported browser_type for {browser_name}: {browser_type}")
        profile_id = str(data.get("profile_id") or "").strip()
        profile_name = str(data.get("profile_name") or "").strip()
        if browser_type == "bitbrowser" and not profile_id:
            raise ConfigError(f"{browser_name}: bitbrowser requires profile_id")
        if browser_type == "donut" and not profile_name:
            raise ConfigError(f"{browser_name}: donut requires profile_name")
        instances.append(
            InstanceConfig(
                browser_name=browser_name,
                browser_type=browser_type,
                profile_id=profile_id,
                profile_name=profile_name,
                auto_restart=bool(data.get("auto_restart", True)),
                priority=int(data.get("priority", 100)),
            )
        )

    return AppConfig(
        central=central,
        watchdog=watchdog,
        browsers=BrowserConfigs(bitbrowser=bitbrowser, donut=donut),
        instances=tuple(instances),
    )
