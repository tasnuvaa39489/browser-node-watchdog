from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from browser_watchdog.adapters import BrowserAdapter, DiscoveredProfile
from browser_watchdog.central import CentralClient
from browser_watchdog.config import AppConfig, load_raw_config


def build_discovered_config(
    config_path: str | Path,
    config: AppConfig,
    central: CentralClient,
    adapters: dict[str, BrowserAdapter],
) -> tuple[dict[str, Any], list[str]]:
    raw = deepcopy(load_raw_config(config_path))
    central_raw = raw.get("central")
    if isinstance(central_raw, dict):
        central_raw.pop("auth_mode", None)
        central_raw.pop("token_env", None)
    browsers_raw = raw.get("browsers")
    if isinstance(browsers_raw, dict):
        donut_raw = browsers_raw.get("donut")
        if isinstance(donut_raw, dict):
            for legacy_key in ("mode", "base_url", "token_env", "request_timeout_seconds"):
                donut_raw.pop(legacy_key, None)
    central_names = set(central.get_ai_status())
    existing_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in raw.get("instances") or []:
        if not isinstance(item, dict):
            continue
        browser_type = str(item.get("browser_type") or "").strip().lower()
        key_value = str(item.get("profile_id") or item.get("profile_name") or "").strip()
        if browser_type and key_value:
            existing_by_key[(browser_type, key_value)] = item

    generated: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for browser_type, adapter in adapters.items():
        for profile in adapter.discover_profiles():
            key_value = profile.profile_id or profile.profile_name
            existing = existing_by_key.get((browser_type, key_value))
            if existing:
                generated.append(existing)
                continue
            exact_match = profile.profile_name in central_names
            browser_name = profile.profile_name
            if not exact_match:
                unresolved.append(f"{browser_type}:{profile.profile_name or profile.profile_id}")
            item: dict[str, Any] = {
                "browser_name": browser_name,
                "browser_type": browser_type,
            }
            if profile.profile_id:
                item["profile_id"] = profile.profile_id
            if profile.profile_name:
                item["profile_name"] = profile.profile_name
            item["auto_restart"] = bool(exact_match)
            item["priority"] = 100
            generated.append(item)

    raw["instances"] = generated
    return raw, unresolved


def write_discovered_config(data: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
