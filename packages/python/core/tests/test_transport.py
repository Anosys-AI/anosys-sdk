"""Tests for size-limited delivery and the bounded retry queue (anosys_sdk_core.transport)."""

import json
import os
import stat
import time

import pytest

from anosys_sdk_core.transport import (
    PendingQueue, chunk_records, deliver, fit_record, is_paused, json_size,
    max_batch_bytes, send_records,
)


class Response:
    def __init__(self, status):
        self.status_code = status


class FakePost:
    """Records each request body; answers with a scripted status or exception."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.bodies = []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.bodies.append(json)
        answer = self.answers.pop(0) if self.answers else 200
        if isinstance(answer, Exception):
            raise answer
        return Response(answer)


def test_default_limit_and_override(monkeypatch):
    monkeypatch.delenv("ANOSYS_MAX_BATCH_BYTES", raising=False)
    assert max_batch_bytes() == 10_000_000
    monkeypatch.setenv("ANOSYS_MAX_BATCH_BYTES", "2000000")
    assert max_batch_bytes() == 2_000_000


def test_chunks_stay_under_limit():
    records = [{"i": i, "text": "x" * 900} for i in range(50)]
    chunks = chunk_records(records, limit=10_000)
    assert sum(len(c) for c in chunks) == 50
    assert all(json_size(c) <= 10_000 for c in chunks)


def test_oversized_record_truncated_raw_first():
    record = {"cvs199": "r" * 50_000, "user_prompt": "p" * 3_000, "session_id": "s"}
    fitted = fit_record(record, limit=20_000)
    assert json_size([fitted]) <= 20_000
    assert "truncated: original 50000 bytes" in fitted["cvs199"]
    assert fitted["user_prompt"] == "p" * 3_000   # untouched: raw truncation was enough
    assert fitted["session_id"] == "s"


def test_unfittable_record_dropped():
    assert fit_record({f"k{i}": i for i in range(5_000)}, limit=2_000) is None


@pytest.mark.parametrize("status,retried", [
    (500, True), (503, True), (429, True), (408, True),
    (400, False), (404, False), (413, False), (422, False),
])
def test_status_classification(status, retried):
    sent, retry, pause = send_records("u", [{"a": 1}], post=FakePost(status))
    assert sent == 0
    assert bool(retry) is retried
    assert pause is None


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_pause(status):
    post = FakePost(status)
    sent, retry, pause = send_records("u", [{"a": 1}] * 3, limit=2_000, post=post)
    assert (sent, retry, pause) == (0, [], status)


def test_network_errors_retried():
    sent, retry, pause = send_records("u", [{"a": 1}], post=FakePost(TimeoutError()))
    assert (sent, len(retry), pause) == (0, 1, None)


def test_queue_bounds(tmp_path):
    queue = PendingQueue(tmp_path / "q.jsonl", max_bytes=2_000, max_age_seconds=60, max_attempts=2)
    queue.save(PendingQueue.entries_for([{"n": i, "pad": "x" * 100} for i in range(50)]))
    entries = queue.load()
    assert 0 < len(entries) < 50 and entries[-1]["record"]["n"] == 49   # newest kept
    assert stat.S_IMODE(os.stat(tmp_path / "q.jsonl").st_mode) == 0o600
    old = [{"record": {"n": 1}, "first_failed": time.time() - 3600, "attempts": 1},
           {"record": {"n": 2}, "first_failed": time.time(), "attempts": 2},
           {"record": {"n": 3}, "first_failed": time.time(), "attempts": 1}]
    queue.save(old)
    assert [e["record"]["n"] for e in queue.load()] == [3]


def test_pre_v2_queue_lines_are_ignored(tmp_path):
    path = tmp_path / "q.jsonl"
    path.write_text(json.dumps({"cvs199": "old bare record"}) + "\n")
    assert PendingQueue(path).load() == []


# Ingestion off / outage / timeout / no network / 413: the queue stays bounded
# and drains once ingestion recovers.
@pytest.mark.parametrize("failure", [500, 503, TimeoutError(), ConnectionError()])
def test_transient_failures_then_recovery(tmp_path, failure):
    queue = PendingQueue(tmp_path / "q.jsonl", max_attempts=5)
    marker = tmp_path / "paused.json"
    for turn in range(3):
        assert deliver("u", [{"turn": turn}], queue, marker, post=FakePost(failure, failure)) == 0
    assert len(queue.load()) == 3
    post = FakePost(200, 200)
    assert deliver("u", [{"turn": 3}], queue, marker, post=post) == 4
    assert queue.load() == [] and not (tmp_path / "q.jsonl").exists()


@pytest.mark.parametrize("status", [401, 403])
def test_ingestion_disabled_stops_collection(tmp_path, status):
    queue = PendingQueue(tmp_path / "q.jsonl")
    marker = tmp_path / "paused.json"
    deliver("u", [{"turn": 1}], queue, marker, post=FakePost(status))
    assert is_paused(marker) and queue.load() == []
    post = FakePost()
    assert deliver("u", [{"turn": 2}], queue, marker, post=post) == 0
    assert post.bodies == []          # nothing built up or sent while paused


@pytest.mark.parametrize("status", [404, 413])
def test_permanent_rejection_never_queues(tmp_path, status):
    queue = PendingQueue(tmp_path / "q.jsonl")
    for turn in range(5):
        deliver("u", [{"turn": turn}], queue, tmp_path / "p.json", post=FakePost(status))
    assert queue.load() == []


def test_attempts_cap_bounds_queue(tmp_path):
    queue = PendingQueue(tmp_path / "q.jsonl", max_attempts=3)
    marker = tmp_path / "p.json"
    for turn in range(10):
        deliver("u", [{"turn": turn}], queue, marker, post=FakePost(*([500] * 20)))
    assert len(queue.load()) <= 3


def test_encrypted_value_is_replaced_whole_not_cut(monkeypatch):
    from anosys_sdk_core.encryption import derive_keys, encrypt, decrypt
    keys = derive_keys("pass", "ws")
    big = encrypt("x" * 5000, keys)
    small = encrypt("keep me", keys)
    out = fit_record({"cvs199": big, "user_prompt": small}, limit=3000)
    assert out["cvs199"].startswith("[truncated: original")
    assert decrypt(out["user_prompt"], keys) == "keep me"


def test_post_record_fits_and_posts():
    from anosys_sdk_core.transport import post_record
    calls = []

    def post(url, json, timeout, headers):
        calls.append(json)
        return "ok"

    assert post_record("u", {"cvs199": "y" * 5000, "a": 1}, post=post) == "ok"
    os.environ["ANOSYS_MAX_BATCH_BYTES"] = "2048"
    try:
        assert post_record("u", {"cvs199": "y" * 5000, "a": 1}, post=post) == "ok"
        assert "truncated" in calls[-1]["cvs199"] and calls[-1]["a"] == 1
    finally:
        del os.environ["ANOSYS_MAX_BATCH_BYTES"]
