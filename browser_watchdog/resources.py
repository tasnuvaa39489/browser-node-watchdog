from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_percent: float
    memory_percent: float
    available_memory_mb: int


@dataclass(frozen=True)
class ResourceDecision:
    allowed: bool
    reason: str
    snapshot: ResourceSnapshot


class ResourceMonitor:
    def __init__(
        self,
        max_cpu_percent: float,
        max_memory_percent: float,
        min_available_memory_mb: int,
        cpu_sample_seconds: float = 1.0,
    ) -> None:
        self.max_cpu_percent = max_cpu_percent
        self.max_memory_percent = max_memory_percent
        self.min_available_memory_mb = min_available_memory_mb
        self.cpu_sample_seconds = cpu_sample_seconds

    def snapshot(self) -> ResourceSnapshot:
        cpu = float(psutil.cpu_percent(interval=self.cpu_sample_seconds))
        memory = psutil.virtual_memory()
        return ResourceSnapshot(
            cpu_percent=cpu,
            memory_percent=float(memory.percent),
            available_memory_mb=int(memory.available / 1024 / 1024),
        )

    def can_start_browser(self) -> ResourceDecision:
        snapshot = self.snapshot()
        if snapshot.cpu_percent >= self.max_cpu_percent:
            return ResourceDecision(False, "high_cpu", snapshot)
        if snapshot.memory_percent >= self.max_memory_percent:
            return ResourceDecision(False, "high_memory_percent", snapshot)
        if snapshot.available_memory_mb < self.min_available_memory_mb:
            return ResourceDecision(False, "low_available_memory", snapshot)
        return ResourceDecision(True, "ok", snapshot)
