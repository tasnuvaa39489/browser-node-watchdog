from types import SimpleNamespace

import pytest

from browser_watchdog.config import CentralConfig, ConfigError
from watchdog import _build_central_client


def app_config(central: CentralConfig):
    return SimpleNamespace(central=central)


def test_central_client_uses_login_credentials(monkeypatch):
    monkeypatch.setenv("AI_COMPARE_PANEL_USERNAME", "watchdog")
    monkeypatch.setenv("AI_COMPARE_PANEL_PASSWORD", "password")

    client = _build_central_client(app_config(CentralConfig("https://server")))

    assert client.username == "watchdog"
    assert client.password == "password"


def test_login_requires_both_username_and_password(monkeypatch):
    monkeypatch.setenv("AI_COMPARE_PANEL_USERNAME", "watchdog")
    monkeypatch.delenv("AI_COMPARE_PANEL_PASSWORD", raising=False)

    with pytest.raises(ConfigError, match="both AI_COMPARE_PANEL_USERNAME"):
        _build_central_client(app_config(CentralConfig("https://server")))
