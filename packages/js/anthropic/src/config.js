// API-key resolution and logging live in anosys-sdk-core (one implementation for
// every package). A missing or unresolvable key disables sending; it never falls
// back to a default site, and the key is never logged.
import { config as loadDotenv } from 'dotenv';
import { createLogger, resolveApiKey } from 'anosys-sdk-core';

loadDotenv();

export { resolveApiKey };
export const log = createLogger('anthropic');
