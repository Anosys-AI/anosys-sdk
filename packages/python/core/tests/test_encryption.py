"""
Unit tests for AnoSys SDK client-side data encryption.
"""

import os
from unittest.mock import patch

import pytest

from anosys_sdk_core.encryption import (
    ANOSYS_ENCRYPTION_PREFIX,
    DEFAULT_ENCRYPTED_COLUMNS,
    derive_256_bit_key,
    encrypt,
    decrypt,
    get_encryption_key,
    get_target_columns,
    encrypt_payload,
)


def test_derive_256_bit_key_length():
    key = derive_256_bit_key("my-secret-key")
    assert isinstance(key, bytes)
    assert len(key) == 32


def test_encryption_sample_vector():
    passphrase = "YOUR_SECRET_KEY_HERE"
    text = "Hello from AnoSys Technologies!"
    derived_key = derive_256_bit_key(passphrase)
    encrypted = encrypt(text, derived_key)
    # Must match the sample vector
    assert encrypted == "J+0Ntn9F5hhtKSBGTFZPce61f8zwRKwrp7bNpwp2Cw4="


def test_encryption_roundtrip():
    passphrase = "passphrase_12345"
    key = derive_256_bit_key(passphrase)
    for text in [
        "Simple ASCII text",
        "Unicode characters: ελληνικά, 🚀, 日本語, español",
        "A" * 16,  # Exact 16-byte boundary
        "B" * 32,  # Exact 32-byte boundary
        "C" * 15,
        "C" * 17,
        "",        # Empty string
    ]:
        cipher_b64 = encrypt(text, key)
        # Prefixed roundtrip
        decrypted = decrypt(f"{ANOSYS_ENCRYPTION_PREFIX}{cipher_b64}", key)
        assert decrypted == text
        # Raw roundtrip
        decrypted_raw = decrypt(cipher_b64, key)
        assert decrypted_raw == text


def test_get_encryption_key_handling():
    with patch.dict(os.environ, {}, clear=True):
        assert get_encryption_key() is None

    with patch.dict(os.environ, {"ANOSYS_ENCRYPTION_KEY": ""}):
        assert get_encryption_key() is None

    with patch.dict(os.environ, {"ANOSYS_ENCRYPTION_KEY": "null"}):
        assert get_encryption_key() is None

    with patch.dict(os.environ, {"ANOSYS_ENCRYPTION_KEY": "none"}):
        assert get_encryption_key() is None

    with patch.dict(os.environ, {"ANOSYS_ENCRYPTION_KEY": "  secret_key  "}):
        assert get_encryption_key() == "secret_key"


def test_get_target_columns_default_and_override():
    with patch.dict(os.environ, {}, clear=True):
        cols = get_target_columns()
        assert "llm_input" in cols
        assert "llm_output" in cols
        assert "gen_ai_input_messages" in cols
        assert "gen_ai_output_messages" in cols
        assert "cvs199" in cols
        assert "user_prompt" in cols
        assert "cvs4" in cols

    with patch.dict(os.environ, {"ANOSYS_ENCRYPTED_COLUMNS": "cvs1, cvs2, cvs199"}):
        cols = get_target_columns()
        assert cols == {"cvs1", "cvs2", "cvs199"}

    # Typo alias support
    with patch.dict(os.environ, {"ANOSYS_ENCRYPTES_COLUMNS": "cvs3,cvs4"}):
        cols = get_target_columns()
        assert cols == {"cvs3", "cvs4"}


def test_encrypt_payload_when_disabled():
    with patch.dict(os.environ, {}, clear=True):
        data = {"llm_input": "hello", "cvs199": "raw", "other": 123}
        result = encrypt_payload(data)
        assert result == {"llm_input": "hello", "cvs199": "raw", "other": 123}


def test_encrypt_payload_default_columns():
    with patch.dict(os.environ, {"ANOSYS_ENCRYPTION_KEY": "test-key"}):
        data = {
            "session_id": "sess-1",
            "llm_input": "What is the capital of Greece?",
            "llm_output": "The capital is Athens.",
            "gen_ai_input_messages": '[{"role": "user", "content": "hi"}]',
            "gen_ai_output_messages": '[{"role": "assistant", "content": "hello"}]',
            "cvs199": '{"full": "context"}',
            "user_prompt": "What is the capital?",
            "cvs4": "What is the capital?",
            "input_tokens": 15,
        }
        res = encrypt_payload(data)

        # Encrypted fields have prefix
        assert res["llm_input"].startswith(ANOSYS_ENCRYPTION_PREFIX)
        assert res["llm_output"].startswith(ANOSYS_ENCRYPTION_PREFIX)
        assert res["gen_ai_input_messages"].startswith(ANOSYS_ENCRYPTION_PREFIX)
        assert res["gen_ai_output_messages"].startswith(ANOSYS_ENCRYPTION_PREFIX)
        assert res["cvs199"].startswith(ANOSYS_ENCRYPTION_PREFIX)
        assert res["user_prompt"].startswith(ANOSYS_ENCRYPTION_PREFIX)
        assert res["cvs4"].startswith(ANOSYS_ENCRYPTION_PREFIX)

        # Non-encrypted fields stay as-is
        assert res["session_id"] == "sess-1"
        assert res["input_tokens"] == 15

        # Verify decryption
        key = derive_256_bit_key("test-key")
        assert decrypt(res["llm_input"], key) == "What is the capital of Greece?"
        assert decrypt(res["llm_output"], key) == "The capital is Athens."


def test_encrypt_payload_override_columns():
    with patch.dict(os.environ, {
        "ANOSYS_ENCRYPTION_KEY": "test-key",
        "ANOSYS_ENCRYPTED_COLUMNS": "custom_col1,custom_col2",
    }):
        data = {
            "custom_col1": "val1",
            "custom_col2": "val2",
            "llm_input": "do not encrypt me",
        }
        res = encrypt_payload(data)
        assert res["custom_col1"].startswith(ANOSYS_ENCRYPTION_PREFIX)
        assert res["custom_col2"].startswith(ANOSYS_ENCRYPTION_PREFIX)
        assert res["llm_input"] == "do not encrypt me"


def test_encrypt_payload_non_string_warning(capsys):
    with patch.dict(os.environ, {
        "ANOSYS_ENCRYPTION_KEY": "test-key",
        "ANOSYS_ENCRYPTED_COLUMNS": "num_col,bool_col,str_col",
    }):
        data = {
            "num_col": 42,
            "bool_col": True,
            "str_col": "valid string",
        }
        res = encrypt_payload(data)
        captured = capsys.readouterr()

        assert "[ANOSYS] Warning: Column 'num_col' contains non-string data (type: int)" in captured.err
        assert "[ANOSYS] Warning: Column 'bool_col' contains non-string data (type: bool)" in captured.err
        assert res["num_col"] == 42
        assert res["bool_col"] is True
        assert res["str_col"].startswith(ANOSYS_ENCRYPTION_PREFIX)


def test_encrypt_payload_idempotency():
    with patch.dict(os.environ, {"ANOSYS_ENCRYPTION_KEY": "test-key"}):
        data = {"llm_input": "initial"}
        res1 = encrypt_payload(data)
        val1 = res1["llm_input"]
        assert val1.startswith(ANOSYS_ENCRYPTION_PREFIX)

        # Second call does not re-encrypt
        res2 = encrypt_payload(res1)
        assert res2["llm_input"] == val1


def test_encrypt_payload_list_of_dicts():
    with patch.dict(os.environ, {"ANOSYS_ENCRYPTION_KEY": "test-key"}):
        records = [
            {"llm_input": "query 1", "session_id": "s1"},
            {"llm_input": "query 2", "session_id": "s2"},
        ]
        res = encrypt_payload(records)
        assert len(res) == 2
        assert res[0]["llm_input"].startswith(ANOSYS_ENCRYPTION_PREFIX)
        assert res[1]["llm_input"].startswith(ANOSYS_ENCRYPTION_PREFIX)
        assert res[0]["session_id"] == "s1"
        assert res[1]["session_id"] == "s2"
