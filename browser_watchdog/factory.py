from __future__ import annotations

from browser_watchdog.adapters import (
    BitBrowserAdapter,
    BrowserAdapter,
    DonutUiaAdapter,
)
from browser_watchdog.config import AppConfig


def build_adapters(config: AppConfig) -> dict[str, BrowserAdapter]:
    adapters: dict[str, BrowserAdapter] = {}
    if config.browsers.bitbrowser.enabled:
        bit = config.browsers.bitbrowser
        adapters["bitbrowser"] = BitBrowserAdapter(
            base_url=bit.base_url,
            timeout_seconds=bit.request_timeout_seconds,
            load_extensions=bit.load_extensions,
        )

    if config.browsers.donut.enabled:
        donut = config.browsers.donut
        adapters["donut"] = DonutUiaAdapter(window_title=donut.window_title)
    return adapters
