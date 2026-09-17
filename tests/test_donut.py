from types import SimpleNamespace

import pytest

from browser_watchdog.adapters import AdapterError
from browser_watchdog.adapters.donut import DonutUiaAdapter


class FakeWindow:
    def __init__(self, title, handle):
        self._title = title
        self.handle = handle

    def window_text(self):
        return self._title


class FakeSpec:
    def __init__(self, wrapper):
        self.wrapper = wrapper

    def wrapper_object(self):
        return self.wrapper


class FakeDesktopInstance:
    def __init__(self, backend, wrapper):
        self.backend = backend
        self.wrapper = wrapper

    def windows(self, **kwargs):
        self.wrapper.window_query = kwargs
        return [
            FakeWindow("Administrator cmd - Donut test", 1),
            FakeWindow("Donut Browser", 2),
        ]

    def window(self, handle):
        assert self.backend == "uia"
        assert handle == 2
        return FakeSpec(self.wrapper)


class FakeDesktop:
    def __init__(self, wrapper):
        self.wrapper = wrapper
        self.backends = []

    def __call__(self, backend):
        self.backends.append(backend)
        return FakeDesktopInstance(backend, self.wrapper)


class FakeDataItem:
    def __init__(self, text):
        self._text = text
        self.element_info = SimpleNamespace(name=text)

    def window_text(self):
        return self._text


class FakeActionItem:
    def __init__(self, default_action):
        self.default_action = default_action
        self.double_clicks = 0
        self.clicks = 0
        self.element_info = SimpleNamespace(element=object())

    def legacy_properties(self):
        return {"DefaultAction": self.default_action}

    def double_click_input(self):
        self.double_clicks += 1

    def click_input(self):
        self.clicks += 1


class FakeUiaWindow:
    def __init__(self, texts=()):
        self.items = [FakeDataItem(text) for text in texts]

    def descendants(self, control_type):
        assert control_type == "DataItem"
        return self.items


def test_get_window_uses_exact_win32_handle_before_uia():
    wrapper = FakeUiaWindow()
    desktop = FakeDesktop(wrapper)
    adapter = DonutUiaAdapter()
    adapter._desktop_and_uia = lambda: (desktop, None)

    assert adapter._get_window() is wrapper
    assert desktop.backends == ["win32", "uia"]
    assert wrapper.window_query == {"visible_only": False}


def test_parse_current_donut_table_rows():
    wrapper = FakeUiaWindow(
        [
            "全选",
            "名称",
            "标签",
            "备注",
            "代理 / VPN",
            "扩展",
            "DNS",
            "停止",
            "FR-DT-HK05-01",
            "无标签",
            "无备注",
            "474 B/s",
            "ai_compare",
            "—",
            "配置文件信息",
            "启动",
            "FR-DT-HK05-02",
            "无标签",
            "无备注",
            "0 B/s",
            "ai_compare",
            "—",
            "配置文件信息",
        ]
    )
    adapter = DonutUiaAdapter()
    adapter._get_window = lambda: wrapper

    profiles = adapter._parse_profiles()

    assert [profile["name"] for profile in profiles] == [
        "FR-DT-HK05-01",
        "FR-DT-HK05-02",
    ]
    assert [profile["is_running"] for profile in profiles] == [True, False]


def test_parse_english_donut_table_rows():
    wrapper = FakeUiaWindow(
        [
            "Select all",
            "Name",
            "Tags",
            "Note",
            "Proxy / VPN",
            "EXT",
            "DNS",
            "",
            "Select profile",
            "Launch",
            "AU-DT-HK3-16",
            "No tags",
            "No Note",
            "AU-01 \u00a0",
            "ai_compare",
            "—",
            "",
            "Profile info",
            "",
            "Stop",
            "AU-DT-HK3-18",
            "No tags",
            "No Note",
            "20.2 KB/s",
            "ai_compare",
            "—",
            "",
            "Profile info",
        ]
    )
    adapter = DonutUiaAdapter()
    adapter._get_window = lambda: wrapper

    profiles = adapter._parse_profiles()

    assert [profile["name"] for profile in profiles] == [
        "AU-DT-HK3-16",
        "AU-DT-HK3-18",
    ]
    assert [profile["is_running"] for profile in profiles] == [False, True]


def test_load_profiles_retries_while_restored_table_is_rendering():
    adapter = DonutUiaAdapter()
    responses = iter([[], [], [{"name": "AU-DT-HK3-16", "is_running": False}]])
    sleeps = []
    adapter._parse_profiles = lambda: next(responses)
    adapter.sleeper = sleeps.append

    profiles = adapter._load_profiles(attempts=3)

    assert profiles == [{"name": "AU-DT-HK3-16", "is_running": False}]
    assert sleeps == [1, 1]


def test_discovery_rejects_empty_donut_table():
    adapter = DonutUiaAdapter()
    adapter._activate_window = lambda: None
    adapter._load_profiles = lambda: []

    with pytest.raises(AdapterError, match="profile table stayed empty"):
        adapter.discover_profiles()


@pytest.mark.parametrize("default_action", ["双击", "Double click"])
def test_trigger_uses_physical_double_click_for_donut_action(default_action):
    adapter = DonutUiaAdapter()
    activations = []
    adapter._activate_window = lambda: activations.append(True)
    button = FakeActionItem(default_action)

    adapter._trigger(button)

    assert activations == [True]
    assert button.double_clicks == 1
    assert button.clicks == 0
