"""Application-SDK sending: background, bounded, never to a default site, nothing in logs."""

import logging
import threading
import time

import pytest

from anosys_sdk_core import config
from anosys_sdk_core.transport import BackgroundSender, post_record


class Resp:
    def __init__(self, status):
        self.status_code = status


def test_missing_key_disables_sending(monkeypatch):
    monkeypatch.delenv("ANOSYS_API_KEY", raising=False)
    monkeypatch.delenv("ANOSYS_API_URL", raising=False)
    assert config.resolve_api_key() == ""
    assert post_record("", {"a": 1}, post=lambda *a, **k: pytest.fail("posted")) is None


def test_explicit_endpoint_without_key(monkeypatch):
    monkeypatch.delenv("ANOSYS_API_KEY", raising=False)
    monkeypatch.setenv("ANOSYS_API_URL", "https://self-hosted.example/ingest")
    assert config.resolve_api_key() == "https://self-hosted.example/ingest"


def test_unresolvable_key_is_not_logged(monkeypatch, caplog):
    def boom(*a, **k):
        raise config.requests.exceptions.ConnectionError("https://resolver?apikey=SECRET-KEY")
    monkeypatch.setattr(config.requests, "get", boom)
    with caplog.at_level(logging.ERROR):
        assert config.resolve_api_key("SECRET-KEY") == ""
    assert "SECRET-KEY" not in caplog.text


def test_sender_does_not_block_and_delivers():
    sender = BackgroundSender(max_queue=10)
    gate = threading.Event()
    posted = []

    def slow_post(url, json, timeout, headers):
        gate.wait(2)
        posted.append(json)
        return Resp(200)

    sender.post = slow_post
    start = time.monotonic()
    assert sender.submit("https://ingest", {"a": 1})
    assert time.monotonic() - start < 0.1      # the caller never waits on the network
    gate.set()
    assert sender.flush(2) and posted == [{"a": 1}]


def test_sender_queue_is_bounded_and_failures_are_contained(caplog):
    sender = BackgroundSender(max_queue=2)
    gate = threading.Event()

    def stuck(url, json, timeout, headers):
        gate.wait(2)
        raise RuntimeError("payload with prompt text")

    sender.post = stuck
    results = [sender.submit("https://ingest", {"i": i}) for i in range(10)]
    assert results.count(False) >= 7           # dropped, memory stays bounded
    gate.set()
    with caplog.at_level(logging.ERROR):
        sender.flush(2)
    assert "prompt text" not in caplog.text    # only the error type is logged


def test_sender_ignores_missing_endpoint():
    sender = BackgroundSender()
    assert sender.submit("", {"a": 1}) is False
