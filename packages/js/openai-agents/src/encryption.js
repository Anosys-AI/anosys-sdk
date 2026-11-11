/**
 * Field encryption lives in anosys-sdk-core (enc2: PBKDF2-SHA256 keys,
 * deterministic AES-256-GCM, workspace salt). Re-exported here so existing
 * imports keep working; there is one implementation for every package.
 */
export {
  ANOSYS_ENCRYPTION_PREFIX,
  DEFAULT_ENCRYPTED_COLUMNS,
  JSON_COLUMNS,
  deriveKeys,
  derive256BitKey,
  encrypt,
  decrypt,
  encryptValue,
  encryptPayload,
  getEncryptionKey,
  getTargetColumns,
} from 'anosys-sdk-core';
