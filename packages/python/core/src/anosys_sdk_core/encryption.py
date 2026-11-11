"""
Client-side encryption of content columns for AnoSys SDK (format ``enc2``).

Only the user's browser can decrypt: the passphrase never leaves the
process that sends the data, and the AnoSys console decrypts in the browser.

Format (shared with the JS packages and the console):

    k_enc, k_nonce = PBKDF2-HMAC-SHA256(passphrase, "anosys-enc2:" + salt,
                                         600,000 iterations, 64 bytes) split in two
    nonce          = HMAC-SHA256(k_nonce, plaintext)[:12]
    ciphertext     = AES-256-GCM(k_enc, nonce, plaintext)   (16-byte tag appended)
    value          = "enc2:" + base64(nonce + ciphertext + tag)

The nonce is derived from the plaintext (a synthetic IV), so encryption is
deterministic: the same value encrypts identically in every column and table
of a workspace. That keeps GROUP BY, COUNT DISTINCT and joins working on
encrypted columns; it reveals only which values are equal. GCM adds tamper
detection, and PBKDF2 makes passphrase guessing slow.

Configuration:
    ANOSYS_ENCRYPTION_KEY      passphrase; encryption is on when set
    ANOSYS_ENCRYPTION_SALT     workspace salt shown in the AnoSys console
                               (default "anosys", with a warning)
    ANOSYS_ENCRYPTED_COLUMNS   comma-separated override of the default columns

Columns that are JSON-typed in BigQuery receive the encrypted value as a JSON
string (``"enc2:..."``) so the row stays valid JSON.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

ANOSYS_ENCRYPTION_PREFIX = "enc2:"
KDF_ITERATIONS = 600_000
KDF_SALT_PREFIX = "anosys-enc2:"
DEFAULT_SALT = "anosys"

# Content columns encrypted by default, across descriptive and CV layouts.
DEFAULT_ENCRYPTED_COLUMNS: List[str] = [
    # prompts, completions and messages
    "llm_input", "llm_output", "llm_system",
    "gen_ai_input_messages", "gen_ai_output_messages", "gen_ai_system_instructions",
    "user_prompt", "userPrompt", "assistant_text", "assistantText", "last_prompt",
    "cvs4", "cvs5", "cvs24",
    # raw records and attribute blobs (they repeat the content)
    "cvs199", "cvs18", "otel_events",
    # tool and file data
    "tool_use_result", "cvs26", "commands", "written_paths", "file_states",
    "cvs90", "cvs91", "cvs76", "cvs77", "cvs78", "cvs79",
    "ide_diagnostics", "cvs30", "file_attachments", "hook_specific_output", "mcp_meta",
    # model-written summaries, task text and errors
    "custom_title", "ai_title", "cvs40", "cvs41", "agent_description", "cvs35",
    "summary_content", "task_description", "cvs65", "origami_summary",
    "status_message", "error_details", "api_error", "error_obj", "cvs25", "cause",
    "research",
]

# Columns stored as JSON in BigQuery: an encrypted value must stay valid JSON
JSON_COLUMNS: Set[str] = {
    "tool_use_result", "error_obj", "ide_diagnostics", "hook_specific_output",
    "file_states", "worktree_session", "staged_nodes", "iterations", "research",
    "mcp_meta", "summarize_metadata", "compact_metadata", "microcompact_metadata",
    "cause", "api_error", "origin", "image_paste_ids", "file_attachments",
    "written_paths", "commands", "server_tool_use",
    "otel_resource", "otel_attributes", "otel_events", "otel_links", "otel_labels",
    "otel_log_attributes", "llm_tools", "llm_token_count", "llm_invocation_parameters",
    "gen_ai_input_messages", "gen_ai_output_messages", "gen_ai_system_instructions",
    "gen_ai_tool_definitions", "gen_ai_request_stop_sequences",
    "gen_ai_request_encoding_formats", "gen_ai_response_finish_reasons",
    "otel_histogram_bucket_counts", "otel_histogram_bucket_bounds",
}

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False

_key_cache: Dict[Tuple[str, str], Tuple[bytes, bytes]] = {}
_warned_default_salt = False


def get_encryption_salt() -> str:
    """Workspace salt from ANOSYS_ENCRYPTION_SALT (default "anosys", warned once)."""
    global _warned_default_salt
    salt = (os.environ.get("ANOSYS_ENCRYPTION_SALT") or "").strip()
    if salt:
        return salt
    if not _warned_default_salt:
        _warned_default_salt = True
        logger.warning("ANOSYS_ENCRYPTION_SALT is not set; using the default salt. "
                       "Set it to the salt shown in the AnoSys console.")
    return DEFAULT_SALT


def derive_keys(passphrase: str, salt: Optional[str] = None) -> Tuple[bytes, bytes]:
    """Derive (k_enc, k_nonce), 32 bytes each, from a passphrase and workspace salt."""
    salt = salt if salt is not None else get_encryption_salt()
    cache_key = (passphrase, salt)
    if cache_key not in _key_cache:
        material = hashlib.pbkdf2_hmac(
            "sha256",
            passphrase.encode("utf-8"),
            (KDF_SALT_PREFIX + salt).encode("utf-8"),
            KDF_ITERATIONS,
            dklen=64,
        )
        _key_cache[cache_key] = (material[:32], material[32:])
    return _key_cache[cache_key]


def derive_256_bit_key(passphrase: str, salt: Optional[str] = None) -> bytes:
    """The 32-byte encryption key for a passphrase (kept for API compatibility)."""
    return derive_keys(passphrase, salt)[0]


def encrypt(text: str, keys: Tuple[bytes, bytes]) -> str:
    """Encrypt text deterministically; returns ``enc2:`` + base64(nonce + ciphertext + tag)."""
    if not _HAS_CRYPTOGRAPHY:
        raise RuntimeError("The 'cryptography' library is required for encryption. Install with: pip install cryptography")
    if not isinstance(keys, (tuple, list)) or len(keys) != 2:
        raise TypeError("encrypt needs both keys: use derive_keys(passphrase, salt)")
    k_enc, k_nonce = keys
    data = text.encode("utf-8")
    nonce = hmac.new(k_nonce, data, hashlib.sha256).digest()[:12]
    sealed = AESGCM(k_enc).encrypt(nonce, data, None)
    return ANOSYS_ENCRYPTION_PREFIX + base64.b64encode(nonce + sealed).decode("ascii")


def _decryption_key(keys: Any) -> bytes:
    """The AES key from ``derive_keys`` output, ``derive_256_bit_key`` output, or a passphrase."""
    if isinstance(keys, (tuple, list)):
        return keys[0]
    if isinstance(keys, (bytes, bytearray)):
        return bytes(keys)
    if isinstance(keys, str):
        return derive_keys(keys)[0]
    raise TypeError("keys must be derive_keys(...), derive_256_bit_key(...) or the passphrase")


def decrypt(value: str, keys: Any) -> str:
    """
    Decrypt an ``enc2:`` value (also accepts the JSON-string form ``"enc2:..."``).
    ``keys`` may be ``derive_keys(passphrase, salt)``, ``derive_256_bit_key(passphrase, salt)``
    or the passphrase itself (with the salt from ANOSYS_ENCRYPTION_SALT).
    """
    if not _HAS_CRYPTOGRAPHY:
        raise RuntimeError("The 'cryptography' library is required for decryption. Install with: pip install cryptography")
    if value.startswith('"'):
        value = json.loads(value)
    if value.startswith(ANOSYS_ENCRYPTION_PREFIX):
        value = value[len(ANOSYS_ENCRYPTION_PREFIX):]
    raw = base64.b64decode(value)
    return AESGCM(_decryption_key(keys)).decrypt(raw[:12], raw[12:], None).decode("utf-8")


def get_encryption_key() -> Optional[str]:
    """The passphrase from ANOSYS_ENCRYPTION_KEY, or None when encryption is off."""
    key = os.environ.get("ANOSYS_ENCRYPTION_KEY")
    if not key or not key.strip() or key.strip().lower() in ("null", "none", "undefined"):
        return None
    return key.strip()


def explicit_target_columns() -> Optional[Set[str]]:
    """ANOSYS_ENCRYPTED_COLUMNS (or the ANOSYS_ENCRYPTES_COLUMNS alias), when set."""
    raw = os.environ.get("ANOSYS_ENCRYPTED_COLUMNS") or os.environ.get("ANOSYS_ENCRYPTES_COLUMNS")
    if raw and raw.strip():
        cols = {col.strip() for col in raw.split(",") if col.strip()}
        if cols:
            return cols
    return None


def get_target_columns(data: Optional[Dict[str, Any]] = None, keep: Optional[Iterable[str]] = None) -> Set[str]:
    """
    Columns to encrypt.

    - ANOSYS_ENCRYPTED_COLUMNS, when set, is used as given.
    - With ``keep`` (the integration's metadata allowlist), every other column
      holding text, a list or an object is encrypted: content is whatever is not
      metadata, so a column cannot be missed because of its name or alias
      (descriptive and cvs* names alike). Numbers and booleans stay readable.
    - Otherwise DEFAULT_ENCRYPTED_COLUMNS.
    """
    explicit = explicit_target_columns()
    if explicit is not None:
        if data is not None:
            mirror_cols = {c for c in ("cvs199", "cvs18", "otel_events") if c in data}
            return explicit | mirror_cols
        return explicit
    if keep is not None and data is not None:
        keep = keep if isinstance(keep, (set, frozenset)) else set(keep)
        return {
            k for k, v in data.items()
            if v is not None and k not in keep and k != "cvs198"
            and not isinstance(v, (bool, int, float))
        }
    return set(DEFAULT_ENCRYPTED_COLUMNS)


def _warn(msg: str) -> None:
    print(msg, file=sys.stderr)
    logger.warning(msg)


def _is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and (
        value.startswith(ANOSYS_ENCRYPTION_PREFIX) or value.startswith('"' + ANOSYS_ENCRYPTION_PREFIX)
    )


def encrypt_value(column: str, value: Any, keys: Tuple[bytes, bytes]) -> Any:
    """Encrypt one column value; objects and arrays are serialized first."""
    if value is None or _is_encrypted(value):
        return value
    text = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"), default=str)
    sealed = encrypt(text, keys)
    return json.dumps(sealed) if column in JSON_COLUMNS else sealed


def encrypt_payload(data: Any, keep: Optional[Iterable[str]] = None) -> Any:
    """
    Encrypt the content columns of a payload dict (or list of dicts) when
    ANOSYS_ENCRYPTION_KEY is set. Returns the payload unchanged otherwise.
    ``keep`` is the integration's metadata allowlist (see get_target_columns).
    """
    if data is None:
        return None
    if isinstance(data, list):
        return [encrypt_payload(item, keep) for item in data]
    if not isinstance(data, dict):
        return data

    passphrase = get_encryption_key()
    if not passphrase:
        return data
    # Encryption was requested: if it cannot be done, the targeted columns are
    # dropped rather than sent in plaintext (fail closed).
    keys = None
    if not _HAS_CRYPTOGRAPHY:
        _warn("[ANOSYS] Warning: ANOSYS_ENCRYPTION_KEY is set but 'cryptography' is not installed; encrypted columns are dropped.")
    else:
        try:
            keys = derive_keys(passphrase)
        except Exception as e:
            _warn(f"[ANOSYS] Warning: Failed to derive encryption key ({e}); encrypted columns are dropped.")

    for col in get_target_columns(data, keep):
        if col not in data or data[col] is None:
            continue
        if keys is None:
            data[col] = None
            continue
        try:
            data[col] = encrypt_value(col, data[col], keys)
        except Exception as e:
            _warn(f"[ANOSYS] Warning: Failed to encrypt column '{col}' ({e}); it is dropped.")
            data[col] = None
    return data
