from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from browser_watchdog.central import CentralClient
from browser_watchdog.config import ConfigError, load_config
from browser_watchdog.discovery import build_discovered_config, write_discovered_config
from browser_watchdog.factory import build_adapters
from browser_watchdog.logging_setup import configure_logging
from browser_watchdog.resources import ResourceMonitor
from browser_watchdog.service import WatchdogService
from browser_watchdog.state import StateStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor and restart local AI browser nodes")
    parser.add_argument("--config", default="config.yaml", help="YAML config path")
    parser.add_argument("--once", action="store_true", help="Run one polling cycle and exit")
    parser.add_argument("--discover", action="store_true", help="Discover local profiles and generate mappings")
    parser.add_argument(
        "--discover-output",
        default="config.discovered.yaml",
        help="Output path used with --discover",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    config_path = Path(args.config).resolve()
    project_dir = config_path.parent
    logger = configure_logging(project_dir / "logs" / "watchdog.log", args.verbose)
    try:
        config = load_config(config_path)
        token = os.getenv(config.central.token_env, "").strip()
        if not token:
            raise ConfigError(f"environment variable {config.central.token_env} is required")
        central = CentralClient(
            config.central.base_url,
            token,
            config.central.request_timeout_seconds,
        )
        adapters = build_adapters(config)

        if args.discover:
            central.check_health()
            discovered, unresolved = build_discovered_config(config_path, config, central, adapters)
            output = Path(args.discover_output)
            if not output.is_absolute():
                output = project_dir / output
            write_discovered_config(discovered, output)
            logger.info("discovery_written path=%s unresolved=%s", output, len(unresolved))
            for item in unresolved:
                logger.warning("discovery_unresolved profile=%s auto_restart=false", item)
            return 0

        resources = ResourceMonitor(
            max_cpu_percent=config.watchdog.max_cpu_percent,
            max_memory_percent=config.watchdog.max_memory_percent,
            min_available_memory_mb=config.watchdog.min_available_memory_mb,
        )
        state = StateStore(project_dir / "state.json")
        service = WatchdogService(config, central, adapters, resources, state, logger)
        if args.once:
            service.run_cycle()
        else:
            service.run_forever()
        return 0
    except KeyboardInterrupt:
        logger.info("watchdog_stopped")
        return 0
    except Exception as exc:
        logger.exception("startup_failed error=%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
