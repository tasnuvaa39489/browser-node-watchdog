from types import SimpleNamespace

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

    def windows(self):
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
