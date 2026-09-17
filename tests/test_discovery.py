from pathlib import Path

from browser_watchdog.config import load_config
from browser_watchdog.discovery import build_discovered_config


class FakeCentral:
    def get_ai_status(self):
        return {}


def test_discovery_removes_legacy_token_and_donut_rest_settings(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
central:
  base_url: https://server
  auth_mode: login
  token_env: OLD_PANEL_TOKEN
browsers:
  donut:
    enabled: true
    mode: rest
    base_url: http://127.0.0.1:10108
    token_env: OLD_DONUT_KEY
    request_timeout_seconds: 30
instances: []
""",
        encoding="utf-8",
    )

    discovered, unresolved = build_discovered_config(
        path,
        load_config(path),
        FakeCentral(),
        {},
    )

    assert "auth_mode" not in discovered["central"]
    assert "token_env" not in discovered["central"]
    assert discovered["browsers"]["donut"] == {"enabled": True}
    assert unresolved == []
