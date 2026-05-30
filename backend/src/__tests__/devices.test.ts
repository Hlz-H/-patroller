import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import request from 'supertest';
import { createApp } from '../app';
import { initDb, closeDb } from '../db';
import { existsSync, mkdirSync, unlinkSync } from 'fs';

process.env.DB_PATH = './data/test-devices.db';
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

describe('POST /api/v1/devices/:id/heartbeat', () => {
  it('registers a device via heartbeat', async () => {
    const res = await request(app)
      .post('/api/v1/devices/dev-001/heartbeat')
      .send({ name: 'Test Device 1', localIp: '192.168.1.10', version: '1.0.0' });
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('success', true);
    expect(res.body).toHaveProperty('timestamp');
    expect(typeof res.body.timestamp).toBe('number');
  });

  it('updates existing device on repeat heartbeat', async () => {
    const res = await request(app)
      .post('/api/v1/devices/dev-001/heartbeat')
      .send({ name: 'Test Device 1 Updated', localIp: '192.168.1.11', version: '1.1.0' });
    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
  });
});

describe('GET /api/v1/devices', () => {
  it('returns all devices', async () => {
    const res = await request(app).get('/api/v1/devices');
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body.length).toBeGreaterThanOrEqual(1);
  });

  it('each device has required fields', async () => {
    const res = await request(app).get('/api/v1/devices');
    const device = res.body.find((d: { id: string }) => d.id === 'dev-001');
    expect(device).toBeDefined();
    expect(device).toHaveProperty('id', 'dev-001');
    expect(device).toHaveProperty('name');
    expect(device).toHaveProperty('lastSeen');
    expect(device).toHaveProperty('status');
    expect(device).toHaveProperty('version');
  });
});

describe('GET /api/v1/devices/online', () => {
  it('returns online devices', async () => {
    const res = await request(app).get('/api/v1/devices/online');
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    const dev001 = res.body.find((d: { id: string }) => d.id === 'dev-001');
    expect(dev001).toBeDefined();
    expect(dev001.status).toBe('online');
  });
});

describe('GET /api/v1/devices/:id', () => {
  it('returns a device by id', async () => {
    const res = await request(app).get('/api/v1/devices/dev-001');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('id', 'dev-001');
  });

  it('returns 404 for non-existent device', async () => {
    const res = await request(app).get('/api/v1/devices/non-existent');
    expect(res.status).toBe(404);
    expect(res.body).toEqual({ error: 'Device not found' });
  });
});

describe('PUT /api/v1/devices/:id', () => {
  it('updates device name', async () => {
    const res = await request(app)
      .put('/api/v1/devices/dev-001')
      .send({ name: 'Renamed Device' });
    expect(res.status).toBe(200);
    expect(res.body.name).toBe('Renamed Device');
  });

  it('updates device config', async () => {
    const res = await request(app)
      .put('/api/v1/devices/dev-001')
      .send({ config: { interval: 60 } });
    expect(res.status).toBe(200);
    expect(res.body.config).toEqual({ interval: 60 });
  });

  it('returns 404 for non-existent device', async () => {
    const res = await request(app)
      .put('/api/v1/devices/non-existent')
      .send({ name: 'Ghost' });
    expect(res.status).toBe(404);
    expect(res.body).toEqual({ error: 'Device not found' });
  });
});

describe('POST /api/v1/devices/:id/metrics', () => {
  it('accepts metrics payload', async () => {
    const metrics = {
      cpu: { percent: 45.2, perCore: [42.0, 48.5] },
      memory: { total: 16000000000, used: 8000000000, percent: 50.0 },
      disk: { total: 512000000000, used: 256000000000, percent: 50.0 },
      network: { bytesSent: 1000000, bytesRecv: 500000 },
    };
    const res = await request(app)
      .post('/api/v1/devices/dev-001/metrics')
      .send(metrics);
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ success: true });
  });
});

describe('POST /api/v1/devices/:id/alerts', () => {
  it('creates an alert for a device', async () => {
    const res = await request(app)
      .post('/api/v1/devices/dev-001/alerts')
      .send({
        type: 'cpu',
        severity: 'warning',
        message: 'CPU usage above 80%',
        details: { threshold: 80, current: 92 },
      });
    expect(res.status).toBe(201);
    expect(res.body).toHaveProperty('id');
    expect(res.body).toHaveProperty('deviceId', 'dev-001');
    expect(res.body).toHaveProperty('type', 'cpu');
    expect(res.body).toHaveProperty('severity', 'warning');
    expect(res.body).toHaveProperty('message', 'CPU usage above 80%');
    expect(res.body).toHaveProperty('acknowledged', false);
  });

  it('returns 400 when missing required fields', async () => {
    const res = await request(app)
      .post('/api/v1/devices/dev-001/alerts')
      .send({ type: 'cpu' });
    expect(res.status).toBe(400);
    expect(res.body).toHaveProperty('error');
  });
});

describe('DELETE /api/v1/devices/:id', () => {
  it('deletes a device', async () => {
    const res = await request(app).delete('/api/v1/devices/dev-001');
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ success: true });
  });

  it('returns 404 when deleting same device again', async () => {
    const res = await request(app).delete('/api/v1/devices/dev-001');
    expect(res.status).toBe(404);
    expect(res.body).toEqual({ error: 'Device not found' });
  });
});
