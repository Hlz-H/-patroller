// WebSocket message handler and routing

import WebSocket from 'ws';
import { WsMessage } from '../types';
import { registerDevice, updateLastSeen, getDevice, insertMetrics } from '../db/devices';
import { storeAlert } from '../db/alerts';
import { processAlert } from '../pipeline/policy';
import { logger } from '../app';

interface WsClient {
  ws: WebSocket;
  deviceId?: string;
  isAlive: boolean;
  subscribedDevices: Set<string>;
}

const clients = new Map<WebSocket, WsClient>();

export function handleConnection(ws: WebSocket, _req: any): void {
  const client: WsClient = {
    ws,
    deviceId: undefined,
    isAlive: true,
    subscribedDevices: new Set(),
  };

  clients.set(ws, client);

  // Heartbeat
  ws.on('pong', () => {
    client.isAlive = true;
  });

  ws.on('message', (rawData: WebSocket.Data) => {
    try {
      const msg: WsMessage = JSON.parse(rawData.toString());
      handleMessage(client, msg);
    } catch {
      ws.send(JSON.stringify({ type: 'error', message: 'Invalid message format' }));
    }
  });

  ws.on('close', () => {
    clients.delete(ws);
  });

  ws.on('error', () => {
    clients.delete(ws);
  });
}

function handleMessage(client: WsClient, msg: WsMessage): void {
  switch (msg.type) {
    case 'register': {
      client.deviceId = msg.deviceId;
      registerDevice(msg.deviceId, msg.name);
      broadcast({
        type: 'device:online',
        deviceId: msg.deviceId,
      });
      break;
    }

    case 'metrics': {
      if (!client.deviceId) break;
      updateLastSeen(client.deviceId);
      insertMetrics(client.deviceId, msg.data as unknown as Record<string, unknown>);
      broadcastToSubscribers(client.deviceId, {
        type: 'device:metrics',
        deviceId: client.deviceId,
        data: msg.data,
      });
      break;
    }

    case 'alert': {
      if (!client.deviceId) break;
      const result = processAlert({ ...msg.data, deviceId: client.deviceId });
      if (result.action === 'suppressed') {
        logger.debug('[pipeline] Alert suppressed: %s', msg.data.message);
        break;
      }
      if (result.action === 'deduplicated') {
        logger.debug('[pipeline] Alert deduplicated: %s', msg.data.message);
        break;
      }
      // result.action === 'stored'
      const alert = storeAlert(result.alert!);
      broadcastToSubscribers(client.deviceId, {
        type: 'device:alert',
        deviceId: client.deviceId,
        data: alert,
      });
      break;
    }

    case 'status': {
      // Status update received - just update lastSeen
      if (!client.deviceId) break;
      updateLastSeen(client.deviceId);
      break;
    }

    case 'subscribe': {
      client.subscribedDevices = new Set(msg.deviceIds);
      break;
    }

    case 'command': {
      // Route command to target device
      const target = findClientByDeviceId(msg.deviceId);
      if (target) {
        target.ws.send(
          JSON.stringify({
            type: 'command',
            deviceId: msg.deviceId, // sender deviceId
            action: msg.action,
            payload: msg.payload,
          })
        );
      }
      break;
    }
  }
}

// Broadcast to all connected clients
export function broadcast(msg: WsMessage): void {
  const data = JSON.stringify(msg);
  for (const [, client] of clients) {
    if (client.ws.readyState === WebSocket.OPEN) {
      client.ws.send(data);
    }
  }
}

// Broadcast to clients subscribed to a specific device
function broadcastToSubscribers(deviceId: string, msg: WsMessage): void {
  const data = JSON.stringify(msg);
  for (const [, client] of clients) {
    if (client.ws.readyState === WebSocket.OPEN) {
      // If client has empty subscriptions, receive all
      if (client.subscribedDevices.size === 0 || client.subscribedDevices.has(deviceId)) {
        client.ws.send(data);
      }
    }
  }
}

// Send message to a specific device by deviceId
export function sendToDevice(deviceId: string, msg: WsMessage): boolean {
  const client = findClientByDeviceId(deviceId);
  if (!client) return false;
  if (client.ws.readyState !== WebSocket.OPEN) return false;
  client.ws.send(JSON.stringify(msg));
  return true;
}

function findClientByDeviceId(deviceId: string): WsClient | undefined {
  for (const [, client] of clients) {
    if (client.deviceId === deviceId && client.ws.readyState === WebSocket.OPEN) {
      return client;
    }
  }
  return undefined;
}

// Heartbeat check - called periodically
export function heartbeatCheck(): void {
  for (const [ws, client] of clients) {
    if (!client.isAlive) {
      clients.delete(ws);
      ws.terminate();
      if (client.deviceId) {
        broadcast({ type: 'device:offline', deviceId: client.deviceId });
      }
      continue;
    }
    client.isAlive = false;
    ws.ping();
  }
}

export function getClientCount(): number {
  return clients.size;
}
