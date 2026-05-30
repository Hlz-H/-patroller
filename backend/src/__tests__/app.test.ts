import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import request from 'supertest';
import { createApp } from '../app';
import { initDb, closeDb } from '../db';
import { existsSync, mkdirSync, unlinkSync } from 'fs';

process.env.DB_PATH = './data/test-app.db';
process.env.TAILSCALE_AUTH = 'false';

const app = createApp();

beforeAll(async () => {
  // Reset shared DB state to ensure test isolation
  closeDb();
  const { config } = await import('../config');
  if (existsSync(config.DB_PATH)) unlinkSync(config.DB_PATH);
  if (!existsSync('./data')) mkdirSync('./data', { recursive: true });
  await initDb();
});

afterAll(() => {
  closeDb();
});

describe('GET /api/v1/health', () => {
  it('returns ok status with uptime, deviceCount, and timestamp', async () => {
    const res = await request(app).get('/api/v1/health');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('status', 'ok');
    expect(res.body).toHaveProperty('uptime');
    expect(typeof res.body.uptime).toBe('number');
    expect(res.body).toHaveProperty('deviceCount');
    expect(typeof res.body.deviceCount).toBe('number');
    expect(res.body).toHaveProperty('timestamp');
    expect(typeof res.body.timestamp).toBe('number');
  });

  it('returns deviceCount as 0 when no devices registered', async () => {
    const res = await request(app).get('/api/v1/health');
    expect(res.body.deviceCount).toBe(0);
  });
});

describe('404 handler', () => {
  it('returns 404 for unknown routes', async () => {
    const res = await request(app).get('/api/v1/nonexistent');
    expect(res.status).toBe(404);
    expect(res.body).toEqual({ error: 'Not found' });
  });
});
