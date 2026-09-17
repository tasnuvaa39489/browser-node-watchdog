from browser_watchdog.adapters.bitbrowser import BitBrowserAdapter
from browser_watchdog.config import InstanceConfig


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.content = b"json"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        return FakeResponse(self.payloads.pop(0))


def test_stopped_profile_is_opened_with_extensions():
    session = FakeSession(
        [
            {"success": True, "data": {"id": "p1", "status": 0}},
            {"success": True, "data": {"ws": "ws://example"}},
        ]
    )
    adapter = BitBrowserAdapter(session=session, sleeper=lambda _: None)
    adapter.restart(InstanceConfig("node", "bitbrowser", profile_id="p1"), 8)
    assert session.calls[-1][0].endswith("/browser/open")
    assert session.calls[-1][1]["loadExtensions"] is True
    assert not any(call[0].endswith("/browser/close") for call in session.calls)


def test_running_profile_is_closed_before_open():
    session = FakeSession(
        [
            {"success": True, "data": {"id": "p1", "status": 1}},
            {"success": True, "data": {}},
            {"success": True, "data": {"ws": "ws://example"}},
        ]
    )
    adapter = BitBrowserAdapter(session=session, sleeper=lambda _: None)
    adapter.restart(InstanceConfig("node", "bitbrowser", profile_id="p1"), 8)
    paths = [call[0].rsplit("/", 2)[-2:] for call in session.calls]
    assert paths == [["browser", "detail"], ["browser", "close"], ["browser", "open"]]
