from __future__ import annotations

import os
from typing import Any

from browser_watchdog.adapters import (
    AdapterError,
    BitBrowserAdapter,
    BrowserAdapter,
    DonutRestAdapter,
    DonutUiaAdapter,
)
from browser_watchdog.config import AppConfig


def build_adapters(config: AppConfig) -> dict[str, BrowserAdapter]:
    adapters: dict[str, Any] = {}
    if config.browsers.bitbrowser.enabled:
        bit = config.browsers.bitbrowser
        adapters["bitbrowser"] = BitBrowserAdapter(
            base_url=bit.base_url,
            timeout_seconds=bit.request_timeout_seconds,
            load_extensions=bit.load_extensions,
        )

    if config.browsers.donut.enabled:
        donut = config.browsers.donut
        token = os.getenv(donut.token_env, "").strip()
        if donut.mode == "rest" or (donut.mode == "auto" and token):
            adapters["donut"] = DonutRestAdapter(
                base_url=donut.base_url,
                token=token,
                timeout_seconds=donut.request_timeout_seconds,
            )
        elif donut.mode in {"uia", "auto"}:
            adapters["donut"] = DonutUiaAdapter(window_title=donut.window_title)
        else:
            raise AdapterError(f"unsupported Donut mode: {donut.mode}")
    return adapters
