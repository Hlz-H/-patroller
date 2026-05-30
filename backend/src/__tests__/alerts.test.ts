import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import request from 'supertest';
import { createApp } from '../app';
import { initDb, closeDb } from '../db';
import { existsSync, mkdirSync, unlinkSync } from 'fs';

process.env.DB_PATH = './data/test-alerts.db';
process.env.TAILSCALE_AUTH = 'false';

const app = createApp();

let alertId: string;

beforeAll(async () => {
  // Reset shared DB state to ensure test isolation
  closeDb();
  const { config } = await import('../config');
  if (existsSync(config.DB_PATH)) unlinkSync(config.DB_PATH);
  if (!existsSync('./data')) mkdirSync('./data', { recursive: true });
  await initDb();

  // Create a device first, then an alert
  await request(app)
    .post('/api/v1/devices/alert-dev-01/heartbeat')
    .send({ name: 'Alert Test Device' });

  const alertRes = await request(app)
    .post('/api/v1/devices/alert-dev-01/alerts')
    .send({
      type: 'memory',
      severity: 'critical',
      message: 'Memory usage above 95%',
      details: { threshold: 95, current: 97 },
    });
  alertId = alertRes.body.id;

  // Create another alert of different type
  await request(app)
    .post('/api/v1/devices/alert-dev-01/alerts')
    .send({
      type: 'disk',
      severity: 'info',
      message: 'Disk usage at 60%',
    });
});

afterAll(() => {
  closeDb();
});

describe('GET /api/v1/alerts', () => {
  it('returns all alerts', async () => {
    const res = await request(app).get('/api/v1/alerts');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('alerts');
    expect(res.body).toHaveProperty('total');
    expect(Array.isArray(res.body.alerts)).toBe(true);
    expect(res.body.total).toBe(2);
    expect(res.body.alerts.length).toBe(2);
  });

  it('filters alerts by deviceId', async () => {
    const res = await request(app).get('/api/v1/alerts?deviceId=alert-dev-01');
    expect(res.status).toBe(200);
    expect(res.body.alerts.every((a: { deviceId: string }) => a.deviceId === 'alert-dev-01')).toBe(true);
  });

  it('filters alerts by type', async () => {
    const res = await request(app).get('/api/v1/alerts?type=memory');
    expect(res.status).toBe(200);
    expect(res.body.total).toBe(1);
    expect(res.body.alerts[0].type).toBe('memory');
  });

  it('filters alerts by severity', async () => {
    const res = await request(app).get('/api/v1/alerts?severity=critical');
    expect(res.status).toBe(200);
    expect(res.body.total).toBe(1);
    expect(res.body.alerts[0].severity).toBe('critical');
  });

  it('respects limit and offset', async () => {
    const res = await request(app).get('/api/v1/alerts?limit=1&offset=0');
    expect(res.status).toBe(200);
    expect(res.body.alerts.length).toBeLessThanOrEqual(1);
  });
});

describe('GET /api/v1/alerts/unacknowledged', () => {
  it('returns unacknowledged count', async () => {
    const res = await request(app).get('/api/v1/alerts/unacknowledged');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('count');
    expect(res.body.count).toBe(2);
  });

  it('filters unacknowledged by deviceId', async () => {
    const res = await request(app).get('/api/v1/alerts/unacknowledged?deviceId=alert-dev-01');
    expect(res.status).toBe(200);
    expect(res.body.count).toBe(2);
  });
});

describe('POST /api/v1/alerts/:id/acknowledge', () => {
  it('acknowledges an alert', async () => {
    const res = await request(app).post(`/api/v1/alerts/${alertId}/acknowledge`);
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ success: true });
  });

  it('reduces unacknowledged count after ack', async () => {
    const res = await request(app).get('/api/v1/alerts/unacknowledged');
    expect(res.body.count).toBe(1);
  });

  it('returns 404 for non-existent alert', async () => {
    const res = await request(app).post('/api/v1/alerts/non-existent-id/acknowledge');
    expect(res.status).toBe(404);
    expect(res.body).toEqual({ error: 'Alert not found' });
  });
});
