import { Worker } from 'bullmq';
import { Server } from 'http';

import { gracefulShutdown } from './gracefulShutdown';
import logger from './logger';

export function setupProcessHandlers(server: Server, workers: Worker[]) {
  process.on('uncaughtException', (err) => {
    logger.error('Uncaught Exception! Shutting down...', {
      name: err.name,
      message: err.message,
    });
    process.exit(1);
  });

  process.on('unhandledRejection', (err: Error) => {
    logger.error('Unhandled Rejection! Shutting down...', {
      err,
      name: err?.name,
      message: err?.message,
    });
    server.close(() => {
      process.exit(1);
    });
  });

  process.once('SIGTERM', async () => await gracefulShutdown(server, workers));
  process.once('SIGINT', async () => await gracefulShutdown(server, workers));
}
