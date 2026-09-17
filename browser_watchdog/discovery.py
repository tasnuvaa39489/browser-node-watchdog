from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from browser_watchdog.adapters import BrowserAdapter, DiscoveredProfile
from browser_watchdog.central import CentralClient
from browser_watchdog.config import AppConfig, load_raw_config


logger = logging.getLogger("browser_watchdog")


def _match_central_browser_name(
    browser_type: str,
    profile_name: str,
    central_names: set[str],
) -> tuple[str | None, str | None]:
    if profile_name in central_names:
        return profile_name, "exact"

    # BitBrowser profiles on some servers omit the machine segment. For example,
    # TH-BT-10 is the local form of TH-BT-HK05-10. Only accept a unique central
    # candidate so discovery cannot silently bind a profile to the wrong server.
    if browser_type != "bitbrowser":
        return None, None
    local_parts = profile_name.split("-")
    if len(local_parts) != 3 or not all(local_parts):
        return None, None

    candidates: list[str] = []
    for central_name in central_names:
        central_parts = central_name.split("-")
        if (
            len(central_parts) == 4
            and all(central_parts)
            and central_parts[0] == local_parts[0]
            and central_parts[1] == local_parts[1]
            and central_parts[3] == local_parts[2]
        ):
            candidates.append(central_name)

    if len(candidates) == 1:
        return candidates[0], "compact"
    return None, None


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
    logger.info("discovery_central_loaded nodes=%s", len(central_names))
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
        logger.info("discovery_browser_started browser=%s", browser_type)
        profiles = adapter.discover_profiles()
        logger.info(
            "discovery_browser_completed browser=%s profiles=%s",
            browser_type,
            len(profiles),
        )
        for profile in profiles:
            key_value = profile.profile_id or profile.profile_name
            existing = existing_by_key.get((browser_type, key_value))
            if existing:
                generated.append(existing)
                continue
            browser_name, match_kind = _match_central_browser_name(
                browser_type,
                profile.profile_name,
                central_names,
            )
            matched = browser_name is not None
            if browser_name is None:
                browser_name = profile.profile_name
                unresolved.append(f"{browser_type}:{profile.profile_name or profile.profile_id}")
            elif match_kind == "compact":
                logger.info(
                    "discovery_compact_match browser=%s profile=%s browser_name=%s",
                    browser_type,
                    profile.profile_name,
                    browser_name,
                )
            item: dict[str, Any] = {
                "browser_name": browser_name,
                "browser_type": browser_type,
            }
            if profile.profile_id:
                item["profile_id"] = profile.profile_id
            if profile.profile_name:
                item["profile_name"] = profile.profile_name
            item["auto_restart"] = matched
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
