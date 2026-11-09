"""Tests for collection levels, consent and field filtering (anosys_sdk_core.privacy)."""

import json
import os
import stat

import pytest

from anosys_sdk_core import privacy
from anosys_sdk_core.privacy import (
    FULL, METADATA, OFF, POLICY_VERSION,
    effective_level, filter_fields, read_consent, write_consent,
)
from anosys_sdk_core.redaction import scrub_secrets


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("ANOSYS_CONSENT_FILE", str(tmp_path / "consent.json"))
    for var in ("ANOSYS_DISABLE", "ANOSYS_COLLECTION_LEVEL", "REDACTION"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_default_is_metadata():
    assert effective_level() == (METADATA, "default")


def test_full_needs_consent_for_current_policy(monkeypatch):
    monkeypatch.setenv("ANOSYS_COLLECTION_LEVEL", "full")
    assert effective_level() == (METADATA, "ANOSYS_COLLECTION_LEVEL (no consent)")
    with pytest.raises(ValueError):
        write_consent(FULL, method="test")
    write_consent(FULL, method="test", accept_policy=POLICY_VERSION)
    assert effective_level()[0] == FULL


def test_old_policy_consent_falls_back(isolated):
    (isolated / "consent.json").write_text(json.dumps({"level": "full", "policy_version": "2000-01-01"}))
    assert effective_level() == (METADATA, "consent (no consent)")


def test_consent_file_is_private_and_readable(isolated):
    write_consent(OFF, method="test")
    assert read_consent()["level"] == OFF
    mode = stat.S_IMODE(os.stat(isolated / "consent.json").st_mode)
    assert mode == 0o600


def test_precedence(monkeypatch, isolated):
    write_consent(FULL, method="test", accept_policy=POLICY_VERSION)
    monkeypatch.setenv("ANOSYS_COLLECTION_LEVEL", "metadata")
    assert effective_level() == (FULL, "consent")             # consent beats env
    assert effective_level("off") == (OFF, "flag")             # flag beats consent
    (isolated / ".anosys").write_text("level=metadata\n")
    assert effective_level() == (METADATA, ".anosys")          # project file lowers
    (isolated / ".anosys").write_text("level=full\n")
    write_consent(METADATA, method="test")
    assert effective_level()[0] == METADATA                    # ...but never raises
    monkeypatch.setenv("ANOSYS_DISABLE", "1")
    assert effective_level("full") == (OFF, "ANOSYS_DISABLE")  # kill switch wins


def test_legacy_redaction_alias(monkeypatch):
    monkeypatch.setenv("REDACTION", "true")
    assert effective_level() == (METADATA, "REDACTION")


def test_filter_fields_by_level():
    record = {"session_id": "s", "input_tokens": 3, "user_prompt": "secret", "brand_new_field": "x"}
    allowed = {"session_id", "input_tokens"}
    assert filter_fields(record, OFF, allowed) == {}
    meta = filter_fields(record, METADATA, allowed)
    assert meta == {"session_id": "s", "input_tokens": 3, "consent": "metadata;none", "cvs198": "metadata;none"}
    full = filter_fields(record, FULL, allowed)
    assert full["user_prompt"] == "secret" and full["brand_new_field"] == "x"
    assert full["consent"] == f"full;{POLICY_VERSION}"
    assert full["cvs198"] == f"full;{POLICY_VERSION}"


def test_unknown_fields_are_excluded_at_metadata():
    assert "brand_new_field" not in filter_fields({"brand_new_field": 1}, METADATA, privacy.BASE_METADATA_FIELDS)


def test_scrub_secrets():
    text = ("key sk-ant-api03-abcdefghijklmnopqrstuvwxyz and AKIAABCDEFGHIJKLMNOP and "
            "password=hunter2hunter2hunter2 and ghp_abcdefghijklmnopqrstuvwxyz0123456789")
    out = scrub_secrets(text)
    for secret in ["sk-ant-api03", "AKIAABCDEFGHIJKLMNOP", "hunter2hunter2", "ghp_abcdef"]:
        assert secret not in out
    assert "password=[SECRET]" in out
    assert scrub_secrets({"a": ["token: abcdefghijklmnop1234"]}) == {"a": ["token: [SECRET]"]}
    assert scrub_secrets("nothing to see here") == "nothing to see here"
