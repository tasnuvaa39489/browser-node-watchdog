from pathlib import Path

from browser_watchdog.adapters import DiscoveredProfile
from browser_watchdog.config import load_config
from browser_watchdog.discovery import build_discovered_config


class FakeCentral:
    def __init__(self, names=()):
        self.names = names

    def get_ai_status(self):
        return {name: {} for name in self.names}


class FakeAdapter:
    def __init__(self, *profiles: DiscoveredProfile):
        self.profiles = profiles

    def discover_profiles(self):
        return list(self.profiles)


def write_minimal_config(path: Path) -> None:
    path.write_text(
        """
central:
  base_url: https://server
instances: []
""",
        encoding="utf-8",
    )


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


def test_discovery_matches_unique_compact_bitbrowser_name(tmp_path: Path):
    path = tmp_path / "config.yaml"
    write_minimal_config(path)
    adapter = FakeAdapter(
        DiscoveredProfile(
            browser_type="bitbrowser",
            profile_id="profile-10",
            profile_name="TH-BT-10",
            running=True,
        )
    )

    discovered, unresolved = build_discovered_config(
        path,
        load_config(path),
        FakeCentral(["TH-BT-HK05-10"]),
        {"bitbrowser": adapter},
    )

    assert discovered["instances"] == [
        {
            "browser_name": "TH-BT-HK05-10",
            "browser_type": "bitbrowser",
            "profile_id": "profile-10",
            "profile_name": "TH-BT-10",
            "auto_restart": True,
            "priority": 100,
        }
    ]
    assert unresolved == []


def test_discovery_keeps_ambiguous_compact_bitbrowser_name_disabled(tmp_path: Path):
    path = tmp_path / "config.yaml"
    write_minimal_config(path)
    adapter = FakeAdapter(
        DiscoveredProfile(
            browser_type="bitbrowser",
            profile_id="profile-10",
            profile_name="TH-BT-10",
            running=False,
        )
    )

    discovered, unresolved = build_discovered_config(
        path,
        load_config(path),
        FakeCentral(["TH-BT-HK04-10", "TH-BT-HK05-10"]),
        {"bitbrowser": adapter},
    )

    assert discovered["instances"][0]["browser_name"] == "TH-BT-10"
    assert discovered["instances"][0]["auto_restart"] is False
    assert unresolved == ["bitbrowser:TH-BT-10"]


def test_discovery_prefers_exact_name_over_compact_match(tmp_path: Path):
    path = tmp_path / "config.yaml"
    write_minimal_config(path)
    adapter = FakeAdapter(
        DiscoveredProfile(
            browser_type="bitbrowser",
            profile_id="profile-10",
            profile_name="TH-BT-10",
            running=True,
        )
    )

    discovered, unresolved = build_discovered_config(
        path,
        load_config(path),
        FakeCentral(["TH-BT-10", "TH-BT-HK05-10"]),
        {"bitbrowser": adapter},
    )

    assert discovered["instances"][0]["browser_name"] == "TH-BT-10"
    assert discovered["instances"][0]["auto_restart"] is True
    assert unresolved == []
