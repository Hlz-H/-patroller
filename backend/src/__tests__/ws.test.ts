import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import http from 'http';
import WebSocket from 'ws';
import { createApp } from '../app';
import { initDb, closeDb } from '../db';
import { attachWebSocket } from '../ws';
import { existsSync, mkdirSync, unlinkSync } from 'fs';

process.env.DB_PATH = './data/test-ws.db';
process.env.TAILSCALE_AUTH = 'false';

const app = createApp();
let server: http.Server;
let port: number;
let wsUrl: string;

beforeAll(async () => {
  // Reset shared DB state to ensure test isolation
  closeDb();
  const { config } = await import('../config');
  if (existsSync(config.DB_PATH)) unlinkSync(config.DB_PATH);
  if (!existsSync('./data')) mkdirSync('./data', { recursive: true });
  await initDb();

  await new Promise<void>((resolve) => {
    server = http.createServer(app);
    attachWebSocket(server);
    server.listen(0, () => {
      const addr = server.address();
      if (addr && typeof addr === 'object') {
        port = addr.port;
        wsUrl = `ws://localhost:${port}/ws`;
      }
      resolve();
    });
  });
});

afterAll(async () => {
  await new Promise<void>((resolve) => {
    if (server) server.close(() => resolve());
    else resolve();
  });
  closeDb();
});

function connectAndWait(ws: WebSocket): Promise<void> {
  return new Promise((resolve, reject) => {
    ws.on('open', resolve);
    ws.on('error', reject);
    setTimeout(() => reject(new Error('Connection timeout')), 5000);
  });
}

function waitForMessage(ws: WebSocket, predicate: (msg: Record<string, unknown>) => boolean): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const handler = (data: WebSocket.Data) => {
      try {
        const msg = JSON.parse(data.toString());
        if (predicate(msg)) {
          ws.removeListener('message', handler);
          resolve(msg);
        }
      } catch {
        // ignore parse errors
      }
    };
    ws.on('message', handler);
    setTimeout(() => {
      ws.removeListener('message', handler);
      reject(new Error('Timeout waiting for message'));
    }, 5000);
  });
}

describe('WebSocket', () => {
  it('should connect and register a device', async () => {
    const ws = new WebSocket(wsUrl);
    await connectAndWait(ws);

    ws.send(JSON.stringify({
      type: 'register',
      deviceId: 'ws-device-1',
      name: 'WS Test Device 1',
    }));

    const msg = await waitForMessage(ws, (m) => m.type === 'device:online');
    expect(msg).toHaveProperty('type', 'device:online');
    expect(msg).toHaveProperty('deviceId', 'ws-device-1');

    ws.close();
  });

  it('should handle metrics message', async () => {
    const ws = new WebSocket(wsUrl);
    await connectAndWait(ws);

    ws.send(JSON.stringify({
      type: 'register',
      deviceId: 'ws-device-2',
      name: 'WS Test Device 2',
    }));

    // Wait for online notification
    await waitForMessage(ws, (m) => m.type === 'device:online' && m.deviceId === 'ws-device-2');

    ws.send(JSON.stringify({
      type: 'metrics',
      data: {
        cpu: { percent: 60.5, perCore: [55.0, 66.0] },
        memory: { total: 16000000000, used: 9600000000, percent: 60.0 },
        disk: { total: 512000000000, used: 307200000000, percent: 60.0 },
        network: { bytesSent: 2000000, bytesRecv: 1000000 },
      },
    }));

    const msg = await waitForMessage(ws, (m) => m.type === 'device:metrics');
    expect(msg).toHaveProperty('type', 'device:metrics');
    expect(msg).toHaveProperty('deviceId', 'ws-device-2');
    expect(msg).toHaveProperty('data');
    expect((msg.data as Record<string, unknown>).cpu).toBeDefined();

    ws.close();
  });

  it('should handle alert message', async () => {
    const ws = new WebSocket(wsUrl);
    await connectAndWait(ws);

    ws.send(JSON.stringify({
      type: 'register',
      deviceId: 'ws-device-3',
      name: 'WS Test Device 3',
    }));

    // Wait for online notification
    await waitForMessage(ws, (m) => m.type === 'device:online' && m.deviceId === 'ws-device-3');

    ws.send(JSON.stringify({
      type: 'alert',
      data: {
        type: 'disk',
        severity: 'warning',
        message: 'Disk space low',
        details: { free: '10GB' },
      },
    }));

    const msg = await waitForMessage(ws, (m) => m.type === 'device:alert');
    expect(msg).toHaveProperty('type', 'device:alert');
    expect(msg).toHaveProperty('deviceId', 'ws-device-3');
    expect(msg).toHaveProperty('data');
    expect((msg.data as Record<string, unknown>).type).toBe('disk');
    expect((msg.data as Record<string, unknown>).severity).toBe('warning');

    ws.close();
  });

  it('should return error for invalid JSON', async () => {
    const ws = new WebSocket(wsUrl);
    await connectAndWait(ws);

    ws.send('not-json');

    const msg = await waitForMessage(ws, (m) => m.type === 'error');
    expect(msg).toHaveProperty('type', 'error');
    expect(msg).toHaveProperty('message', 'Invalid message format');

    ws.close();
  });
});
