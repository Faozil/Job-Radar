from __future__ import annotations

import io
import json
import urllib.error

import pytest

from jobradar import http


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body=None, headers=None):
    payload = io.BytesIO(json.dumps(body or {}).encode())
    return urllib.error.HTTPError("https://x", code, "error", headers or {}, payload)


def install(monkeypatch, *outcomes):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(json.dumps(outcome).encode())

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_only_https_is_allowed():
    with pytest.raises(ValueError):
        http.get_json("http://example.com")


def test_get_json_sends_a_user_agent(monkeypatch):
    calls = install(monkeypatch, {"jobs": []})
    assert http.get_json("https://example.com/jobs") == {"jobs": []}
    assert calls[0].get_header("User-agent").startswith("job-radar/")


def test_404_raises_not_found(monkeypatch):
    install(monkeypatch, http_error(404))
    with pytest.raises(http.NotFoundError):
        http.get_json("https://example.com/missing")


def test_server_errors_are_retried(monkeypatch):
    waits = []
    install(monkeypatch, http_error(503), http_error(502), {"ok": True})
    assert http.get_json("https://example.com", sleep=waits.append) == {"ok": True}
    assert waits == [1.0, 2.0]


def test_retry_after_header_is_respected(monkeypatch):
    waits = []
    install(monkeypatch, http_error(429, headers={"Retry-After": "7"}), {"ok": True})
    assert http.get_json("https://example.com", sleep=waits.append) == {"ok": True}
    assert waits == [7.0]


def test_client_errors_are_not_retried(monkeypatch):
    calls = install(monkeypatch, http_error(400, {"message": "unknown board"}))
    with pytest.raises(http.FetchError, match="HTTP 400 unknown board"):
        http.get_json("https://example.com/boards/x")
    assert len(calls) == 1


def test_network_errors_give_up_after_retries(monkeypatch):
    install(monkeypatch, *[urllib.error.URLError("no route")] * 3)
    with pytest.raises(http.FetchError, match="no route"):
        http.get_json("https://example.com", sleep=lambda _: None)


def test_non_json_response(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse(b"<html>oops</html>")

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(http.FetchError, match="not JSON"):
        http.get_json("https://example.com")
