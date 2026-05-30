import { createServer } from 'http';
import { initDb, closeDb } from './db';
import { createApp, logger } from './app';
import { attachWebSocket } from './ws';
import { markStaleDevicesOffline } from './db/devices';
import { config } from './config';

async function main(): Promise<void> {
  logger.info('Starting Patroller Backend...');

  logger.info({ path: config.DB_PATH }, 'Initializing database');
  await initDb();

  const app = createApp();
  const server = createServer(app);
  attachWebSocket(server);

  const STALE_TIMEOUT_MS = 5 * 60 * 1000;
  const cleanupInterval = setInterval(() => {
    try {
      const count = markStaleDevicesOffline(STALE_TIMEOUT_MS);
      if (count > 0) {
        logger.info({ count }, 'Marked stale devices offline');
      }
    } catch (err) {
      logger.error({ err }, 'Cleanup error');
    }
  }, 60000);

  function shutdown(signal: string): void {
    logger.info({ signal }, 'Shutting down...');
    clearInterval(cleanupInterval);
    server.close(() => {
      closeDb();
      logger.info('Shutdown complete');
      process.exit(0);
    });

    setTimeout(() => {
      logger.error('Forced shutdown after timeout');
      process.exit(1);
    }, 10000);
  }

  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));

  server.listen(config.PORT, () => {
    logger.info({ port: config.PORT }, 'Patroller Backend is running');
    logger.info(`Health check: http://localhost:${config.PORT}/api/v1/health`);
    logger.info(`WebSocket: ws://localhost:${config.PORT}/ws`);
  });
}

main().catch((err) => {
  logger.error({ err }, 'Fatal startup error');
  process.exit(1);
});
