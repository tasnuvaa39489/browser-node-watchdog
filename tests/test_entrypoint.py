from types import SimpleNamespace

import pytest

from browser_watchdog.config import CentralConfig, ConfigError
from watchdog import _build_central_client


def app_config(central: CentralConfig):
    return SimpleNamespace(central=central)


def test_auto_auth_prefers_login_when_credentials_are_present(monkeypatch):
    monkeypatch.setenv("AI_COMPARE_PANEL_USERNAME", "watchdog")
    monkeypatch.setenv("AI_COMPARE_PANEL_PASSWORD", "password")
    monkeypatch.setenv("AI_COMPARE_PANEL_TOKEN", "stale-token")

    client = _build_central_client(app_config(CentralConfig("https://server")))

    assert client.auth_mode == "login"
    assert client.username == "watchdog"


def test_auto_auth_uses_bearer_when_only_token_is_present(monkeypatch):
    monkeypatch.delenv("AI_COMPARE_PANEL_USERNAME", raising=False)
    monkeypatch.delenv("AI_COMPARE_PANEL_PASSWORD", raising=False)
    monkeypatch.setenv("AI_COMPARE_PANEL_TOKEN", "api-token")

    client = _build_central_client(app_config(CentralConfig("https://server")))

    assert client.auth_mode == "bearer"
    assert client.headers == {"Authorization": "Bearer api-token"}


def test_login_requires_both_username_and_password(monkeypatch):
    monkeypatch.setenv("AI_COMPARE_PANEL_USERNAME", "watchdog")
    monkeypatch.delenv("AI_COMPARE_PANEL_PASSWORD", raising=False)

    with pytest.raises(ConfigError, match="both AI_COMPARE_PANEL_USERNAME"):
        _build_central_client(app_config(CentralConfig("https://server")))
