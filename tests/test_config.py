from pathlib import Path

import pytest

from browser_watchdog.config import ConfigError, load_config


def write_config(path: Path, instances: str) -> None:
    path.write_text(
        f"""
central:
  base_url: http://127.0.0.1:8080
instances:
{instances}
""",
        encoding="utf-8",
    )


def test_load_config_accepts_bitbrowser_instance(tmp_path: Path):
    path = tmp_path / "config.yaml"
    write_config(
        path,
        """  - browser_name: AU-DT-HK3-17
    browser_type: bitbrowser
    profile_id: abc
""",
    )
    config = load_config(path)
    assert config.central.base_url == "http://127.0.0.1:8080"
    assert config.instances[0].profile_id == "abc"
    assert config.instances[0].auto_restart is True


def test_duplicate_browser_name_is_rejected(tmp_path: Path):
    path = tmp_path / "config.yaml"
    write_config(
        path,
        """  - browser_name: node-1
    browser_type: bitbrowser
    profile_id: one
  - browser_name: node-1
    browser_type: bitbrowser
    profile_id: two
""",
    )
    with pytest.raises(ConfigError, match="duplicate browser_name"):
        load_config(path)


def test_bitbrowser_requires_profile_id(tmp_path: Path):
    path = tmp_path / "config.yaml"
    write_config(
        path,
        """  - browser_name: node-1
    browser_type: bitbrowser
""",
    )
    with pytest.raises(ConfigError, match="requires profile_id"):
        load_config(path)
