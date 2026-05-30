import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import pino from 'pino';
import { config } from './config';
import deviceRoutes from './api/devices';
import alertRoutes from './api/alerts';
import relayRoutes from './api/relay';
import sandboxRoutes from './api/sandbox';
import { getAllDevices, getMetricsHistory } from './db/devices';

// ── Push notification token store (in-memory) ──────────────────────────
// Persisted to DB is a future improvement.  For now this lets the mobile
// app register for pushes without requiring a schema migration.
const pushTokens = new Set<string>();

export function getPushTokens(): string[] {
  return [...pushTokens];
}

export const logger = pino({
  level: config.LOG_LEVEL,
  ...(process.env.NODE_ENV !== 'production' && !process.env.PATROLLER_SEA
    ? {
        transport: {
          target: 'pino-pretty',
          options: {
            colorize: true,
            translateTime: 'SYS:standard',
            ignore: 'pid,hostname',
          },
        },
      }
    : {}),
});

export function createApp(): express.Application {
  const app = express();

  app.use(
    cors({
      origin: config.CORS_ORIGINS === '*' ? '*' : config.CORS_ORIGINS.split(',').map((s) => s.trim()),
    })
  );
  app.use(express.json());

  app.use((req: Request, _res: Response, next: NextFunction) => {
    logger.debug({ method: req.method, url: req.url }, 'request');
    next();
  });

  app.get('/api/v1/health', (_req: Request, res: Response) => {
    try {
      const deviceCount = getAllDevices().length;
      res.json({
        status: 'ok',
        uptime: process.uptime(),
        deviceCount,
        timestamp: Date.now(),
      });
    } catch {
      res.json({
        status: 'ok',
        uptime: process.uptime(),
        deviceCount: 0,
        timestamp: Date.now(),
      });
    }
  });

  app.get('/api/v1/metrics/history', (req: Request, res: Response) => {
    try {
      const minutes = parseInt(req.query.minutes as string, 10) || 60;
      const records = getMetricsHistory(Math.min(minutes, 1440));
      res.json({ records, total: records.length });
    } catch (err) {
      res.status(500).json({ error: 'Failed to fetch metrics history' });
    }
  });

  app.post('/api/v1/notifications/register', (req: Request, res: Response) => {
    const { token, deviceId } = req.body;
    if (!token) {
      res.status(400).json({ error: 'token is required' });
      return;
    }
    pushTokens.add(token);
    logger.info({ token: token.slice(0, 20) + '…', deviceId }, 'Push token registered');
    res.json({ success: true });
  });

  app.use('/api/v1/devices', deviceRoutes);
  app.use('/api/v1/alerts', alertRoutes);
  app.use('/api/v1/relay', relayRoutes);
  app.use('/api/v1/sandbox', sandboxRoutes);

  app.use((_req: Request, res: Response) => {
    res.status(404).json({ error: 'Not found' });
  });

  app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
    logger.error({ err }, 'Unhandled error');
    res.status(500).json({ error: 'Internal server error' });
  });

  return app;
}
