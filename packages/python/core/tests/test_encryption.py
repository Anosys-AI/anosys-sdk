"""
Unit tests for AnoSys SDK client-side encryption (format enc2).

The sample vector below is shared with the JS packages and the console, so
all three must produce and read the same ciphertext.
"""

import json

import pytest

from anosys_sdk_core import encryption
from anosys_sdk_core.encryption import (
    ANOSYS_ENCRYPTION_PREFIX,
    DEFAULT_ENCRYPTED_COLUMNS,
    JSON_COLUMNS,
    decrypt,
    derive_keys,
    encrypt,
    encrypt_payload,
    get_encryption_key,
    get_target_columns,
)

PASSPHRASE = "YOUR_SECRET_KEY_HERE"
SALT = "workspace-123"
SAMPLE_TEXT = "Hello from AnoSys Technologies!"
SAMPLE_CIPHERTEXT = "enc2:QwYbSu12pZL4oSf17Bb5zJUkGjoRc3wL66HwlsbjlJ5sLJWIHWGlgz7f+PXh4yem/EvB20sQjSg+R4A="


@pytest.fixture
def keys():
    return derive_keys(PASSPHRASE, SALT)


def test_key_derivation_sample_vector(keys):
    assert keys[0].hex() == "965524765751a794f7875a9204f50c7b2970260ecf1f280fed1f317f3ea19493"
    assert keys[1].hex() == "b758d25c8ede925a56cd6af9c51967d453ae5152f9fab13c1fa9619ee1bfe55b"


def test_encryption_sample_vector(keys):
    assert encrypt(SAMPLE_TEXT, keys) == SAMPLE_CIPHERTEXT
    assert decrypt(SAMPLE_CIPHERTEXT, keys) == SAMPLE_TEXT


def test_deterministic_so_grouping_and_joins_work(keys):
    assert encrypt("same prompt", keys) == encrypt("same prompt", keys)
    assert encrypt("same prompt", keys) != encrypt("other prompt", keys)


def test_salt_and_passphrase_change_the_ciphertext(keys):
    assert encrypt(SAMPLE_TEXT, derive_keys(PASSPHRASE, "other-workspace")) != SAMPLE_CIPHERTEXT
    assert encrypt(SAMPLE_TEXT, derive_keys("another passphrase", SALT)) != SAMPLE_CIPHERTEXT


def test_roundtrip_unicode_and_empty(keys):
    for text in ["", "ünïcödé ✓ 日本語", "x" * 10_000]:
        assert decrypt(encrypt(text, keys), keys) == text


def test_tampering_is_detected(keys):
    raw = SAMPLE_CIPHERTEXT[:-6] + ("AAAA==" if not SAMPLE_CIPHERTEXT.endswith("AAAA==") else "BBBB==")
    with pytest.raises(Exception):
        decrypt(raw, keys)


def test_get_encryption_key(monkeypatch):
    monkeypatch.delenv("ANOSYS_ENCRYPTION_KEY", raising=False)
    assert get_encryption_key() is None
    for empty in ["", "  ", "null", "None", "undefined"]:
        monkeypatch.setenv("ANOSYS_ENCRYPTION_KEY", empty)
        assert get_encryption_key() is None
    monkeypatch.setenv("ANOSYS_ENCRYPTION_KEY", " secret ")
    assert get_encryption_key() == "secret"


def test_target_columns_default_and_override(monkeypatch):
    monkeypatch.delenv("ANOSYS_ENCRYPTED_COLUMNS", raising=False)
    monkeypatch.delenv("ANOSYS_ENCRYPTES_COLUMNS", raising=False)
    assert get_target_columns() == set(DEFAULT_ENCRYPTED_COLUMNS)
    monkeypatch.setenv("ANOSYS_ENCRYPTED_COLUMNS", "a, b")
    assert get_target_columns() == {"a", "b"}


def test_default_columns_cover_all_content():
    for col in ["cvs18", "commands", "written_paths", "file_states", "ai_title",
                "custom_title", "agent_description", "error_details", "tool_use_result", "cvs199"]:
        assert col in DEFAULT_ENCRYPTED_COLUMNS


def test_encrypt_payload_off_without_key(monkeypatch):
    monkeypatch.delenv("ANOSYS_ENCRYPTION_KEY", raising=False)
    payload = {"user_prompt": "hello"}
    assert encrypt_payload(payload) == {"user_prompt": "hello"}


def test_encrypt_payload_strings_objects_and_json_columns(monkeypatch, keys):
    monkeypatch.setenv("ANOSYS_ENCRYPTION_KEY", PASSPHRASE)
    monkeypatch.setenv("ANOSYS_ENCRYPTION_SALT", SALT)
    monkeypatch.delenv("ANOSYS_ENCRYPTED_COLUMNS", raising=False)
    payload = {
        "user_prompt": SAMPLE_TEXT,
        "tool_use_result": '{"stdout":"secret output"}',
        "commands": ["rm -rf build"],
        "input_tokens": 12,
        "session_id": "s1",
    }
    out = encrypt_payload(payload)
    assert out["user_prompt"] == SAMPLE_CIPHERTEXT
    # JSON-typed columns carry a JSON string, so BigQuery JSON columns accept them
    assert out["tool_use_result"].startswith('"' + ANOSYS_ENCRYPTION_PREFIX)
    assert "tool_use_result" in JSON_COLUMNS
    assert json.loads(out["tool_use_result"]).startswith(ANOSYS_ENCRYPTION_PREFIX)
    assert decrypt(out["tool_use_result"], keys) == '{"stdout":"secret output"}'
    # arrays/objects are serialized, not skipped
    assert decrypt(out["commands"], keys) == '["rm -rf build"]'
    assert out["input_tokens"] == 12 and out["session_id"] == "s1"


def test_encrypt_payload_is_idempotent(monkeypatch):
    monkeypatch.setenv("ANOSYS_ENCRYPTION_KEY", PASSPHRASE)
    monkeypatch.setenv("ANOSYS_ENCRYPTION_SALT", SALT)
    once = encrypt_payload({"user_prompt": SAMPLE_TEXT, "commands": "[1]"})
    twice = encrypt_payload(dict(once))
    assert once == twice


def test_encrypt_payload_list(monkeypatch):
    monkeypatch.setenv("ANOSYS_ENCRYPTION_KEY", PASSPHRASE)
    monkeypatch.setenv("ANOSYS_ENCRYPTION_SALT", SALT)
    out = encrypt_payload([{"llm_input": SAMPLE_TEXT}, {"llm_input": SAMPLE_TEXT}])
    assert out[0]["llm_input"] == out[1]["llm_input"] == SAMPLE_CIPHERTEXT


def test_fails_closed_without_cryptography(monkeypatch):
    monkeypatch.setenv("ANOSYS_ENCRYPTION_KEY", PASSPHRASE)
    monkeypatch.setattr(encryption, "_HAS_CRYPTOGRAPHY", False)
    out = encrypt_payload({"user_prompt": "plain secret", "session_id": "s1"})
    assert out["user_prompt"] is None
    assert out["session_id"] == "s1"
