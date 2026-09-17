from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from browser_watchdog.adapters import BrowserAdapter
from browser_watchdog.central import CentralClient, CentralServiceError
from browser_watchdog.config import AppConfig, InstanceConfig
from browser_watchdog.resources import ResourceMonitor
from browser_watchdog.state import StateStore


def local_now() -> datetime:
    return datetime.now().astimezone()


def parse_server_time(value: Any, local_tz=None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_tz or local_now().tzinfo)
    return parsed


class WatchdogService:
    def __init__(
        self,
        config: AppConfig,
        central: CentralClient,
        adapters: dict[str, BrowserAdapter],
        resources: ResourceMonitor,
        state: StateStore,
        logger: logging.Logger,
        *,
        clock: Callable[[], datetime] = local_now,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.central = central
        self.adapters = adapters
        self.resources = resources
        self.state = state
        self.logger = logger
        self.clock = clock
        self.sleeper = sleeper

    def run_forever(self) -> None:
        self.logger.info(
            "watchdog_started poll_seconds=%s stale_minutes=%s instances=%s",
            self.config.watchdog.poll_seconds,
            self.config.watchdog.stale_minutes,
            len(self.config.instances),
        )
        while True:
            try:
                self.run_cycle()
            except Exception:
                self.logger.exception("cycle_unhandled_error")
            self.sleeper(self.config.watchdog.poll_seconds)

    def run_cycle(self) -> int:
        try:
            self.central.check_health()
            statuses = self.central.get_ai_status()
        except CentralServiceError as exc:
            self.logger.error("central_unavailable action=none error=%s", exc)
            return 0

        restart_attempts = 0
        ordered = sorted(enumerate(self.config.instances), key=lambda item: (item[1].priority, item[0]))
        for _, instance in ordered:
            status = statuses.get(instance.browser_name)
            if status is None:
                self.logger.error(
                    "node=%s result=MANUAL_REQUIRED reason=node_missing",
                    instance.browser_name,
                )
                continue
            if bool(status.get("banned")):
                self.logger.warning("node=%s action=none reason=banned", instance.browser_name)
                continue

            now = self.clock()
            updated_at = parse_server_time(status.get("updateTime"), now.tzinfo)
            if updated_at is None:
                self.logger.error(
                    "node=%s result=MANUAL_REQUIRED reason=invalid_update_time value=%r",
                    instance.browser_name,
                    status.get("updateTime"),
                )
                continue
            age_seconds = max(0.0, (now - updated_at.astimezone(now.tzinfo)).total_seconds())
            age_minutes = int(age_seconds // 60)
            if age_seconds < self.config.watchdog.stale_minutes * 60:
                self.logger.info("node=%s age=%sm action=none", instance.browser_name, age_minutes)
                continue
            if not instance.auto_restart:
                self.logger.error(
                    "node=%s age=%sm result=MANUAL_REQUIRED reason=auto_restart_disabled",
                    instance.browser_name,
                    age_minutes,
                )
                continue
            if restart_attempts >= self.config.watchdog.max_restarts_per_cycle:
                self.logger.warning(
                    "node=%s age=%sm action=deferred reason=cycle_restart_limit",
                    instance.browser_name,
                    age_minutes,
                )
                continue
            if self._in_cooldown(instance, now):
                self.logger.error(
                    "node=%s age=%sm result=MANUAL_REQUIRED reason=restart_cooldown",
                    instance.browser_name,
                    age_minutes,
                )
                continue

            adapter = self.adapters.get(instance.browser_type)
            if adapter is None:
                self.logger.error(
                    "node=%s result=MANUAL_REQUIRED reason=adapter_disabled browser_type=%s",
                    instance.browser_name,
                    instance.browser_type,
                )
                continue

            decision = self.resources.can_start_browser()
            snapshot = decision.snapshot
            if not decision.allowed:
                self.logger.error(
                    "node=%s result=MANUAL_REQUIRED reason=%s cpu=%.1f memory=%.1f available_mb=%s",
                    instance.browser_name,
                    decision.reason,
                    snapshot.cpu_percent,
                    snapshot.memory_percent,
                    snapshot.available_memory_mb,
                )
                continue

            restart_attempts += 1
            restart_started_at = now
            self.state.mark_restart(instance.browser_name, restart_started_at)
            self.logger.warning(
                "node=%s age=%sm action=restart browser=%s cpu=%.1f memory=%.1f available_mb=%s",
                instance.browser_name,
                age_minutes,
                instance.browser_type,
                snapshot.cpu_percent,
                snapshot.memory_percent,
                snapshot.available_memory_mb,
            )
            try:
                adapter.restart(instance, self.config.watchdog.browser_stop_delay_seconds)
            except Exception as exc:
                self.state.mark_result(instance.browser_name, "MANUAL_REQUIRED", f"restart_failed: {exc}")
                self.logger.exception(
                    "node=%s result=MANUAL_REQUIRED reason=restart_failed error=%s",
                    instance.browser_name,
                    exc,
                )
                continue

            self.sleeper(self.config.watchdog.verify_wait_seconds)
            self._verify_recovery(instance, restart_started_at)
        return restart_attempts

    def _in_cooldown(self, instance: InstanceConfig, now: datetime) -> bool:
        last_restart = self.state.get_last_restart(instance.browser_name)
        if last_restart is None:
            return False
        if last_restart.tzinfo is None:
            last_restart = last_restart.replace(tzinfo=now.tzinfo)
        return now - last_restart.astimezone(now.tzinfo) < timedelta(
            minutes=self.config.watchdog.restart_cooldown_minutes
        )

    def _verify_recovery(self, instance: InstanceConfig, restart_started_at: datetime) -> None:
        try:
            statuses = self.central.get_ai_status()
        except CentralServiceError as exc:
            self.state.mark_result(instance.browser_name, "MANUAL_REQUIRED", f"verify_failed: {exc}")
            self.logger.error(
                "node=%s result=MANUAL_REQUIRED reason=verify_central_unavailable error=%s",
                instance.browser_name,
                exc,
            )
            return
        status = statuses.get(instance.browser_name)
        if status is None:
            self.state.mark_result(instance.browser_name, "MANUAL_REQUIRED", "node_missing_after_restart")
            self.logger.error(
                "node=%s result=MANUAL_REQUIRED reason=node_missing_after_restart",
                instance.browser_name,
            )
            return
        updated_at = parse_server_time(status.get("updateTime"), restart_started_at.tzinfo)
        if updated_at and updated_at > restart_started_at:
            self.state.mark_result(instance.browser_name, "RECOVERED")
            self.logger.info(
                "node=%s result=RECOVERED new_update_time=%s",
                instance.browser_name,
                updated_at.isoformat(),
            )
            return
        self.state.mark_result(instance.browser_name, "MANUAL_REQUIRED", "heartbeat_not_restored")
        self.logger.error(
            "node=%s result=MANUAL_REQUIRED reason=heartbeat_not_restored update_time=%r",
            instance.browser_name,
            status.get("updateTime"),
        )
