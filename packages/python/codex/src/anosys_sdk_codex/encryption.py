"""
Client-side encryption utilities for AnoSys Codex integration.

Supports AES-256-CBC encryption of sensitive telemetry columns
(prompts, completions, messages, raw context) before sending to AnoSys BE.
"""

import base64
import hashlib
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

ANOSYS_ENCRYPTION_PREFIX = "enc:"

DEFAULT_ENCRYPTED_COLUMNS: List[str] = [
    # Primary requested columns
    "llm_input",
    "llm_output",
    "gen_ai_input_messages",
    "gen_ai_output_messages",
    "cvs199",
    # System instructions and legacy system fields
    "gen_ai_system_instructions",
    "llm_system",
    # User prompts and assistant responses across SDKs
    "user_prompt",
    "userPrompt",
    "assistant_text",
    "assistantText",
    "cvs4",
    "cvs5",
    # Multi-turn prompt context and tool execution results
    "last_prompt",
    "cvs24",
    "tool_use_result",
    "cvs26",
    # Additional task / speech prompt fields
    "cvs65",
    "task_description",
    "summary_content",
]

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False


def derive_256_bit_key(passphrase: str) -> bytes:
    """Derive a 256-bit (32-byte) key from a passphrase using SHA-256."""
    sha256 = hashlib.sha256()
    sha256.update(passphrase.encode("utf-8"))
    return sha256.digest()[:32]


def encrypt(text: str, key: bytes) -> str:
    """
    Encrypt text with AES-256-CBC using a zero IV and PKCS#7 padding.
    Returns standard Base64-encoded ciphertext.
    """
    if not _HAS_CRYPTOGRAPHY:
        raise RuntimeError("The 'cryptography' library is required for encryption. Install with: pip install cryptography")

    iv = b"\x00" * 16
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()

    text_bytes = text.encode("utf-8")
    padding_length = 16 - (len(text_bytes) % 16)
    padded_bytes = text_bytes + (bytes([padding_length]) * padding_length)

    encrypted = encryptor.update(padded_bytes) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("utf-8")


def decrypt(prefixed_or_raw: str, key: bytes) -> str:
    """
    Decrypt Base64 ciphertext with or without 'enc:' prefix.
    """
    if not _HAS_CRYPTOGRAPHY:
        raise RuntimeError("The 'cryptography' library is required for decryption. Install with: pip install cryptography")

    raw_b64 = prefixed_or_raw
    if raw_b64.startswith(ANOSYS_ENCRYPTION_PREFIX):
        raw_b64 = raw_b64[len(ANOSYS_ENCRYPTION_PREFIX):]

    encrypted_bytes = base64.b64decode(raw_b64)
    iv = b"\x00" * 16
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted_bytes) + decryptor.finalize()
    if not decrypted:
        return ""
    padding_length = decrypted[-1]
    if padding_length > 16 or padding_length <= 0:
        return decrypted.decode("utf-8")
    return decrypted[:-padding_length].decode("utf-8")


def get_encryption_key() -> Optional[str]:
    """Retrieve the encryption key from ANOSYS_ENCRYPTION_KEY env var if present and not null."""
    key = os.environ.get("ANOSYS_ENCRYPTION_KEY")
    if not key or not key.strip() or key.strip().lower() in ("null", "none", "undefined"):
        return None
    return key.strip()


def get_target_columns() -> Set[str]:
    """
    Retrieve columns to encrypt.
    If ANOSYS_ENCRYPTED_COLUMNS or ANOSYS_ENCRYPTES_COLUMNS is provided,
    it overrides the default list.
    """
    raw = os.environ.get("ANOSYS_ENCRYPTED_COLUMNS") or os.environ.get("ANOSYS_ENCRYPTES_COLUMNS")
    if raw and raw.strip():
        cols = {col.strip() for col in raw.split(",") if col.strip()}
        if cols:
            return cols
    return set(DEFAULT_ENCRYPTED_COLUMNS)


def encrypt_payload(data: Any) -> Any:
    """
    Encrypt targeted fields in a payload dict (or list of dicts) if ANOSYS_ENCRYPTION_KEY is configured.
    Warns on non-string values and skips them.
    """
    if data is None:
        return None

    if isinstance(data, list):
        return [encrypt_payload(item) for item in data]

    if not isinstance(data, dict):
        return data

    key_str = get_encryption_key()
    if not key_str:
        return data

    if not _HAS_CRYPTOGRAPHY:
        msg = "[ANOSYS] Warning: ANOSYS_ENCRYPTION_KEY is set but 'cryptography' library is not installed. Skipping encryption."
        print(msg, file=sys.stderr)
        logger.warning(msg)
        return data

    try:
        derived_key = derive_256_bit_key(key_str)
    except Exception as e:
        msg = f"[ANOSYS] Warning: Failed to derive encryption key: {e}"
        print(msg, file=sys.stderr)
        logger.warning(msg)
        return data

    target_columns = get_target_columns()

    for col in target_columns:
        if col not in data:
            continue
        val = data[col]
        if val is None:
            continue
        if not isinstance(val, str):
            warn_msg = f"[ANOSYS] Warning: Column '{col}' contains non-string data (type: {type(val).__name__}). Skipping encryption."
            print(warn_msg, file=sys.stderr)
            logger.warning(warn_msg)
            continue
        if val.startswith(ANOSYS_ENCRYPTION_PREFIX):
            continue
        try:
            data[col] = f"{ANOSYS_ENCRYPTION_PREFIX}{encrypt(val, derived_key)}"
        except Exception as e:
            warn_msg = f"[ANOSYS] Warning: Failed to encrypt column '{col}': {e}"
            print(warn_msg, file=sys.stderr)
            logger.warning(warn_msg)

    return data
