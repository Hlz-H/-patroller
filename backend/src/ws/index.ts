// WebSocket server setup

import { Server as HttpServer } from 'http';
import WebSocket, { WebSocketServer } from 'ws';
import { handleConnection, heartbeatCheck } from './handler';
import { verifyWebSocketAuth } from '../auth/tailscale';
import { logger } from '../app';

let wss: WebSocketServer | null = null;

export function attachWebSocket(server: HttpServer): WebSocketServer {
  wss = new WebSocketServer({ server, path: '/ws' });

  wss.on('connection', (ws: WebSocket, req) => {
    if (!verifyWebSocketAuth(req)) {
      ws.close(4001, 'Unauthorized');
      return;
    }

    logger.info('WebSocket client connected');
    handleConnection(ws, req);
  });

  // Heartbeat every 30 seconds
  const heartbeatInterval = setInterval(() => {
    heartbeatCheck();
  }, 30000);

  wss.on('close', () => {
    clearInterval(heartbeatInterval);
  });

  logger.info('WebSocket server attached on /ws');
  return wss;
}

export function getWss(): WebSocketServer | null {
  return wss;
}

export { broadcast, sendToDevice, getClientCount } from './handler';
