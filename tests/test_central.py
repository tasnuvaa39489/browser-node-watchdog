import requests

from browser_watchdog.central import CentralClient, CentralServiceError


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self.payload


class FakeCookies:
    def __init__(self):
        self.clear_calls = 0

    def clear(self):
        self.clear_calls += 1


class FakeSession:
    def __init__(self, post_responses=(), get_responses=()):
        self.post_responses = list(post_responses)
        self.get_responses = list(get_responses)
        self.post_calls = []
        self.get_calls = []
        self.cookies = FakeCookies()

    def post(self, url, json, timeout):
        self.post_calls.append((url, json, timeout))
        return self.post_responses.pop(0)

    def get(self, url, headers, timeout):
        self.get_calls.append((url, headers, timeout))
        return self.get_responses.pop(0)


def status_payload():
    return {"browsers": [{"browserName": "node-1", "updateTime": "2026-09-17T10:00:00"}]}


def test_login_mode_logs_in_once_and_reuses_session():
    session = FakeSession(
        post_responses=[FakeResponse({"ok": True})],
        get_responses=[FakeResponse(status_payload()), FakeResponse(status_payload())],
    )
    client = CentralClient(
        "https://server",
        session=session,
        auth_mode="login",
        username="watchdog",
        password="secret",
    )

    assert "node-1" in client.get_ai_status()
    assert "node-1" in client.get_ai_status()
    assert len(session.post_calls) == 1
    assert session.get_calls[0][1] == {}


def test_login_mode_reauthenticates_once_after_401():
    session = FakeSession(
        post_responses=[FakeResponse({"ok": True}), FakeResponse({"ok": True})],
        get_responses=[FakeResponse({}, 401), FakeResponse(status_payload())],
    )
    client = CentralClient(
        "https://server",
        session=session,
        auth_mode="login",
        username="watchdog",
        password="secret",
    )

    assert "node-1" in client.get_ai_status()
    assert len(session.post_calls) == 2
    assert len(session.get_calls) == 2
    assert session.cookies.clear_calls == 1


def test_login_failure_does_not_expose_password():
    session = FakeSession(post_responses=[FakeResponse({}, 401)])
    client = CentralClient(
        "https://server",
        session=session,
        auth_mode="login",
        username="watchdog",
        password="super-secret-password",
    )

    try:
        client.get_ai_status()
    except CentralServiceError as exc:
        assert "super-secret-password" not in str(exc)
    else:
        raise AssertionError("login failure should raise CentralServiceError")


def test_bearer_mode_keeps_existing_behavior():
    session = FakeSession(get_responses=[FakeResponse(status_payload())])
    client = CentralClient(
        "https://server",
        token="api-token",
        session=session,
        auth_mode="bearer",
    )

    assert "node-1" in client.get_ai_status()
    assert session.post_calls == []
    assert session.get_calls[0][1] == {"Authorization": "Bearer api-token"}
