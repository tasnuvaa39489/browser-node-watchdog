from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from browser_watchdog.config import InstanceConfig


class AdapterError(RuntimeError):
    """Raised when a local browser manager operation fails."""


@dataclass(frozen=True)
class DiscoveredProfile:
    browser_type: str
    profile_id: str
    profile_name: str
    running: bool


class BrowserAdapter(Protocol):
    def restart(self, instance: InstanceConfig, stop_delay_seconds: int) -> None: ...

    def discover_profiles(self) -> list[DiscoveredProfile]: ...
