'use strict';

/**
 * API-key resolution and logging shared by the JS application SDKs — the JS side
 * of Python `anosys_sdk_core/config.py`.
 *
 * resolveApiKey returns the ingestion URL for the key, or null when there is no
 * key or it cannot be resolved: nothing is sent then (telemetry is never posted to
 * a default site), and the key never appears in logs.
 */

const RESOLVER_URL = () => process.env.ANOSYS_RESOLVER_URL || 'https://console.anosys.ai/api/resolveapikeys';
const LEVELS = { debug: 0, info: 1, warn: 2, error: 3, silent: 4 };

/** A namespaced logger that respects ANOSYS_LOG_LEVEL (debug|info|warn|error|silent). */
function createLogger(name) {
  const level = () => LEVELS[String(process.env.ANOSYS_LOG_LEVEL || '').toLowerCase()] ?? LEVELS.warn;
  const tag = `[anosys:${name}]`;
  return {
    debug: (...a) => level() <= 0 && console.debug(tag, ...a),
    info: (...a) => level() <= 1 && console.info(tag, ...a),
    warn: (...a) => level() <= 2 && console.warn(tag, ...a),
    error: (...a) => level() <= 3 && console.error(tag, ...a),
  };
}

const log = createLogger('core');

async function resolveApiKey(apiKey = null, timeout = 10000) {
  const key = apiKey ?? process.env.ANOSYS_API_KEY;
  if (!key) {
    const explicit = (process.env.ANOSYS_API_URL || '').trim();
    if (explicit) return explicit; // a self-hosted endpoint set on purpose
    log.warn('ANOSYS_API_KEY not found; AnoSys telemetry is disabled. Get a key at https://console.anosys.ai/collect/integrationoptions');
    return null;
  }
  try {
    const url = new URL(RESOLVER_URL());
    url.searchParams.set('apikey', key);
    const res = await fetch(url, { signal: AbortSignal.timeout(timeout) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data?.apiUrl) log.error('The AnoSys API key was not recognised; telemetry is disabled');
    return data?.apiUrl || null;
  } catch (e) {
    log.error(`Could not resolve the AnoSys API key (${e?.name || 'Error'}); telemetry is disabled`);
    return null;
  }
}

module.exports = { createLogger, resolveApiKey };
