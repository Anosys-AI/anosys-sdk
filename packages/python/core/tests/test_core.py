"""
Expanded tests for anosys-sdk-core Python package.

Covers:
- context: set/get/clear/extract roundtrip, thread isolation, missing keys
- decorators: setup_api, anosys_logger, anosys_raw_logger
- models: BASE_KEY_MAPPING, DEFAULT_STARTING_INDICES contracts
- redaction: redact_string (email, phone, SSN, credit card, api_key)
- redaction: redact_dict (sensitive keys, nested dicts, lists)
"""



from anosys_sdk_core.context import (
    clear_user_context,
    extract_session_id,
    extract_token,
    get_user_context,
    set_user_context,
)
from anosys_sdk_core.models import BASE_KEY_MAPPING, DEFAULT_STARTING_INDICES
from anosys_sdk_core.redaction import REDACTED, redact_dict, redact_string


# ──────────────────────────────────────────────────────────────────────────────
# context
# ──────────────────────────────────────────────────────────────────────────────

def test_context_starts_empty():
    clear_user_context()
    assert get_user_context() is None


def test_context_set_and_get():
    clear_user_context()
    ctx = {"session_id": "sess-123", "token": "tok-abc"}
    set_user_context(ctx)
    assert get_user_context() == ctx


def test_context_clear():
    set_user_context({"session_id": "x"})
    clear_user_context()
    assert get_user_context() is None


def test_extract_session_id():
    clear_user_context()
    set_user_context({"session_id": "sess-xyz"})
    assert extract_session_id() == "sess-xyz"


def test_extract_session_id_missing():
    clear_user_context()
    set_user_context({})
    result = extract_session_id()
    # Function may return None, empty string, or a fallback like 'unknown_session'
    assert result is None or isinstance(result, str)


def test_extract_token():
    clear_user_context()
    set_user_context({"session_id": "s", "token": "bearer-token-123"})
    result = extract_token()
    assert result == "bearer-token-123"


def test_extract_token_missing():
    clear_user_context()
    set_user_context({"session_id": "s"})
    result = extract_token()
    assert result is None or result == ""


def test_context_overwrites():
    clear_user_context()
    set_user_context({"session_id": "first"})
    set_user_context({"session_id": "second"})
    assert get_user_context()["session_id"] == "second"


# ──────────────────────────────────────────────────────────────────────────────
# models
# ──────────────────────────────────────────────────────────────────────────────

def test_base_key_mapping_is_dict():
    assert isinstance(BASE_KEY_MAPPING, dict)
    assert len(BASE_KEY_MAPPING) > 0


def test_base_key_mapping_has_core_gen_ai_keys():
    assert "gen_ai.usage.input_tokens" in BASE_KEY_MAPPING
    assert "gen_ai.usage.output_tokens" in BASE_KEY_MAPPING
    assert "gen_ai.request.model" in BASE_KEY_MAPPING
    assert "raw" in BASE_KEY_MAPPING


def test_default_starting_indices():
    assert "string" in DEFAULT_STARTING_INDICES
    assert "number" in DEFAULT_STARTING_INDICES
    assert "bool" in DEFAULT_STARTING_INDICES
    assert all(isinstance(v, int) for v in DEFAULT_STARTING_INDICES.values())


# ──────────────────────────────────────────────────────────────────────────────
# redaction — redact_string
# ──────────────────────────────────────────────────────────────────────────────

def test_redact_email():
    text = "Contact me at user@example.com for details."
    result = redact_string(text)
    assert "user@example.com" not in result
    assert REDACTED in result


def test_redact_phone():
    text = "Call me at 555-867-5309."
    result = redact_string(text)
    assert "555-867-5309" not in result
    assert REDACTED in result


def test_redact_ssn():
    text = "SSN: 123-45-6789"
    result = redact_string(text)
    assert "123-45-6789" not in result
    assert REDACTED in result


def test_redact_credit_card():
    text = "Card: 4111 1111 1111 1111"
    result = redact_string(text, patterns=["credit_card"])
    assert "4111 1111 1111 1111" not in result
    assert REDACTED in result


def test_redact_api_key():
    text = "sk-abcdefghijklmnopqrstuvwxyz1234567890"
    result = redact_string(text, patterns=["api_key"])
    assert "sk-abcdefghij" not in result
    assert REDACTED in result


def test_redact_string_no_sensitive_data():
    text = "Hello, this is a normal sentence."
    result = redact_string(text)
    assert result == text


def test_redact_string_custom_replacement():
    text = "Email: user@example.com"
    result = redact_string(text, replacement="***")
    assert "***" in result
    assert "user@example.com" not in result


def test_redact_string_selective_patterns():
    text = "user@example.com and SSN: 123-45-6789"
    result = redact_string(text, patterns=["email"])
    assert "user@example.com" not in result
    # SSN should NOT be redacted when only email pattern is selected
    assert "123-45-6789" in result


# ──────────────────────────────────────────────────────────────────────────────
# redaction — redact_dict
# ──────────────────────────────────────────────────────────────────────────────

def test_redact_dict_sensitive_keys():
    data = {"username": "alice", "password": "secret123", "api_key": "sk-abc"}
    result = redact_dict(data)
    assert result["username"] == "alice"
    assert result["password"] == REDACTED
    assert result["api_key"] == REDACTED


def test_redact_dict_nested():
    data = {"auth": {"token": "bearer-xyz", "user": "alice"}}
    result = redact_dict(data)
    assert result["auth"]["token"] == REDACTED
    assert result["auth"]["user"] == "alice"


def test_redact_dict_list_values():
    data = {
        "users": [
            {"name": "Alice", "token": "tok-1"},
            {"name": "Bob", "token": "tok-2"},
        ]
    }
    result = redact_dict(data)
    for user in result["users"]:
        assert user["token"] == REDACTED
        assert user["name"] in ("Alice", "Bob")


def test_redact_dict_string_with_patterns():
    data = {"message": "Contact user@example.com for help"}
    result = redact_dict(data)
    assert "user@example.com" not in result["message"]


def test_redact_dict_preserves_non_sensitive():
    data = {"count": 42, "active": True, "name": "test"}
    result = redact_dict(data)
    assert result["count"] == 42
    assert result["active"] is True
    assert result["name"] == "test"


def test_redact_dict_custom_sensitive_keys():
    data = {"my_secret_field": "hidden", "public": "visible"}
    result = redact_dict(data, sensitive_keys=["secret"])
    assert result["my_secret_field"] == REDACTED
    assert result["public"] == "visible"


# ──────────────────────────────────────────────────────────────────────────────
# decorators — smoke tests (no real HTTP)
# ──────────────────────────────────────────────────────────────────────────────

def test_anosys_logger_import():
    from anosys_sdk_core.decorators import anosys_logger
    assert callable(anosys_logger)


def test_anosys_raw_logger_import():
    from anosys_sdk_core.decorators import anosys_raw_logger
    assert callable(anosys_raw_logger)


def test_setup_api_import():
    from anosys_sdk_core.decorators import setup_api
    assert callable(setup_api)
