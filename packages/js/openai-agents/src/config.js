import axios from 'axios';
import { config as loadDotenv } from 'dotenv';

loadDotenv();

export const DEFAULT_API_URL = process.env.ANOSYS_API_URL ?? 'https://www.anosys.ai';
const API_KEY_RESOLVER_URL = process.env.ANOSYS_RESOLVER_URL ?? 'https://console.anosys.ai/api/resolveapikeys';

export async function resolveApiKey(apiKey = null, timeout = 30000) {
  const key = apiKey ?? process.env.ANOSYS_API_KEY;
  if (!key) {
    log.warn('ANOSYS_API_KEY not found. Obtain your key from https://console.anosys.ai/collect/integrationoptions');
    return DEFAULT_API_URL;
  }
  try {
    const res = await axios.get(`${API_KEY_RESOLVER_URL}?apikey=${key}`, { timeout });
    return res.data?.url ?? DEFAULT_API_URL;
  } catch (e) {
    log.error('Failed to resolve API key:', e.message);
    return DEFAULT_API_URL;
  }
}

const LEVELS = { debug: 0, info: 1, warn: 2, error: 3, silent: 4 };
const currentLevel = LEVELS[process.env.ANOSYS_LOG_LEVEL?.toLowerCase()] ?? LEVELS.warn;

export const log = {
  debug: (...a) => currentLevel <= 0 && console.debug('[anosys:openai-agents]', ...a),
  info:  (...a) => currentLevel <= 1 && console.info('[anosys:openai-agents]', ...a),
  warn:  (...a) => currentLevel <= 2 && console.warn('[anosys:openai-agents]', ...a),
  error: (...a) => currentLevel <= 3 && console.error('[anosys:openai-agents]', ...a),
};
