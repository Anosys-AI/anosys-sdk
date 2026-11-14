<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-white-darkmode.svg">
      <img src="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# anosys-sdk-core (Node.js)

Shared building blocks for every AnoSys Node.js package. You normally don't install it directly; the integration packages depend on it.

- **Collection levels and consent** (`effectiveLevel`, `filterFields`, `writeConsent`): coding-agent hooks collect `metadata` by default. `full` content needs acceptance of the current AnoSys data-collection policy.
- **Size-limited delivery** (`chunkRecords`, `sendRecords`, `deliver`, `PendingQueue`): every request body stays under `ANOSYS_MAX_BATCH_BYTES`, which defaults to 10,000,000 bytes. Permanent errors are dropped, and transient ones are retried from a bounded queue. A 401 or 403 pauses collection.
- **Client-side encryption** (`encryptPayload`, format `enc2`): set `ANOSYS_ENCRYPTION_KEY` and `ANOSYS_ENCRYPTION_SALT`. Encryption is deterministic, so grouping and joins keep working, and only your browser can decrypt. See [DATA_CONTROLS.md](../../../docs/DATA_CONTROLS.md).
- **Secret scrubbing** (`scrubSecrets`): a best-effort removal of API keys and tokens.

Python equivalent: `anosys-sdk-core` on PyPI (`anosys_sdk_core.privacy`, `.transport`, `.encryption`). Both produce identical output.
