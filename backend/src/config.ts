import { existsSync } from 'fs';
import { resolve } from 'path';

function readEnv(): Record<string, string> {
  const envPath = resolve(__dirname, '..', '.env');
  if (!existsSync(envPath)) return {};

  const fs = require('fs');
  const content = fs.readFileSync(envPath, 'utf-8');
  const result: Record<string, string> = {};

  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const value = trimmed.slice(eqIdx + 1).trim();
    result[key] = value;
  }

  return result;
}

const env = { ...readEnv(), ...(process.env as Record<string, string>) };

export const config = {
  PORT: parseInt(env.PORT || '3099', 10),
  DB_PATH: env.DB_PATH || './data/patroller.db',
  TAILSCALE_AUTH: env.TAILSCALE_AUTH === 'true',
  LOG_LEVEL: env.LOG_LEVEL || 'info',
  CORS_ORIGINS: env.CORS_ORIGINS || '*',
};
