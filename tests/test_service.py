import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from browser_watchdog.config import (
    AppConfig,
    BrowserConfigs,
    CentralConfig,
    InstanceConfig,
    WatchdogConfig,
)
from browser_watchdog.resources import ResourceDecision, ResourceSnapshot
from browser_watchdog.service import WatchdogService, parse_server_time
from browser_watchdog.state import StateStore


NOW = datetime(2026, 9, 17, 10, 0, tzinfo=timezone(timedelta(hours=8)))


class FakeCentral:
    def __init__(self, status_batches, health_error=None):
        self.status_batches = list(status_batches)
        self.health_error = health_error
        self.calls = 0

    def check_health(self):
        if self.health_error:
            raise self.health_error
        return {"status": "running"}

    def get_ai_status(self):
        index = min(self.calls, len(self.status_batches) - 1)
        self.calls += 1
        return self.status_batches[index]


class FakeAdapter:
    def __init__(self):
        self.restarted = []

    def restart(self, instance, stop_delay_seconds):
        self.restarted.append((instance.browser_name, stop_delay_seconds))

    def discover_profiles(self):
        return []


class FakeResources:
    def __init__(self, allowed=True, reason="ok"):
        self.decision = ResourceDecision(
            allowed,
            reason,
            ResourceSnapshot(cpu_percent=10, memory_percent=20, available_memory_mb=8192),
        )

    def can_start_browser(self):
        return self.decision


def make_config(*instances):
    return AppConfig(
        central=CentralConfig("http://server"),
        watchdog=WatchdogConfig(
            stale_minutes=30,
            verify_wait_seconds=1,
            restart_cooldown_minutes=60,
            max_restarts_per_cycle=1,
            browser_stop_delay_seconds=8,
        ),
        browsers=BrowserConfigs(),
        instances=tuple(instances),
    )


def make_logger():
    logger = logging.getLogger(f"test-watchdog-{id(object())}")
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    return logger


def build_service(tmp_path: Path, config, central, adapter, resources):
    return WatchdogService(
        config,
        central,
        {"bitbrowser": adapter},
        resources,
        StateStore(tmp_path / "state.json"),
        make_logger(),
        clock=lambda: NOW,
        sleeper=lambda _: None,
    )


def test_parse_server_time_applies_local_timezone_to_naive_value():
    parsed = parse_server_time("2026-09-17T09:00:00", NOW.tzinfo)
    assert parsed == datetime(2026, 9, 17, 9, 0, tzinfo=NOW.tzinfo)


def test_healthy_node_is_not_restarted(tmp_path: Path):
    instance = InstanceConfig("node-1", "bitbrowser", profile_id="p1")
    central = FakeCentral([{"node-1": {"browserName": "node-1", "updateTime": NOW.isoformat()}}])
    adapter = FakeAdapter()
    service = build_service(tmp_path, make_config(instance), central, adapter, FakeResources())
    assert service.run_cycle() == 0
    assert adapter.restarted == []


def test_stale_node_restarts_once_and_verifies_new_heartbeat(tmp_path: Path):
    instance = InstanceConfig("node-1", "bitbrowser", profile_id="p1")
    central = FakeCentral(
        [
            {"node-1": {"browserName": "node-1", "updateTime": (NOW - timedelta(hours=1)).isoformat()}},
            {"node-1": {"browserName": "node-1", "updateTime": (NOW + timedelta(minutes=1)).isoformat()}},
        ]
    )
    adapter = FakeAdapter()
    state = StateStore(tmp_path / "state.json")
    service = WatchdogService(
        make_config(instance),
        central,
        {"bitbrowser": adapter},
        FakeResources(),
        state,
        make_logger(),
        clock=lambda: NOW,
        sleeper=lambda _: None,
    )
    assert service.run_cycle() == 1
    assert adapter.restarted == [("node-1", 8)]
    assert state.data["instances"]["node-1"]["last_result"] == "RECOVERED"


def test_high_resource_usage_blocks_restart(tmp_path: Path):
    instance = InstanceConfig("node-1", "bitbrowser", profile_id="p1")
    central = FakeCentral(
        [{"node-1": {"browserName": "node-1", "updateTime": (NOW - timedelta(hours=1)).isoformat()}}]
    )
    adapter = FakeAdapter()
    service = build_service(
        tmp_path,
        make_config(instance),
        central,
        adapter,
        FakeResources(False, "high_cpu"),
    )
    assert service.run_cycle() == 0
    assert adapter.restarted == []


def test_only_one_stale_node_is_restarted_per_cycle(tmp_path: Path):
    first = InstanceConfig("node-au", "bitbrowser", profile_id="p1", priority=10)
    second = InstanceConfig("node-us", "bitbrowser", profile_id="p2", priority=20)
    stale = (NOW - timedelta(hours=1)).isoformat()
    central = FakeCentral(
        [
            {
                "node-au": {"browserName": "node-au", "updateTime": stale},
                "node-us": {"browserName": "node-us", "updateTime": stale},
            },
            {
                "node-au": {"browserName": "node-au", "updateTime": (NOW + timedelta(minutes=1)).isoformat()},
                "node-us": {"browserName": "node-us", "updateTime": stale},
            },
        ]
    )
    adapter = FakeAdapter()
    service = build_service(tmp_path, make_config(first, second), central, adapter, FakeResources())
    assert service.run_cycle() == 1
    assert adapter.restarted == [("node-au", 8)]
