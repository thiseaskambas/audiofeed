import { Worker } from 'bullmq';
import { Server } from 'http';
import { Socket } from 'net';

import logger from './logger';

const connections: Socket[] = [];

export function trackConnections(server: Server) {
  server.on('connection', (connection) => {
    connections.push(connection);
    connection.on('close', () => {
      const idx = connections.indexOf(connection);
      if (idx !== -1) connections.splice(idx, 1);
    });
  });
}

export async function gracefulShutdown(
  server: Server,
  workers: Worker[],
  timeout = 10000
) {
  logger.info('Received kill signal, shutting down gracefully');

  const forceExitTimeout = setTimeout(() => {
    logger.error(
      'Could not close connections in time, forcefully shutting down'
    );
    process.exit(1);
  }, timeout);

  try {
    await Promise.all(
      workers.map(async (worker) => {
        try {
          await worker.close();
          logger.info(`Closed worker: ${worker.name}`);
        } catch (err) {
          logger.error(`Error closing worker ${worker.name}`, { err });
        }
      })
    );
  } catch (err) {
    logger.error('Error during worker cleanup', { err });
  }

  connections.forEach((curr) => curr.end());

  server.close(() => {
    logger.info('Closed out remaining connections');
    clearTimeout(forceExitTimeout);

    setTimeout(() => {
      connections.forEach((curr) => {
        if (!curr.destroyed) curr.destroy();
      });
      process.exit(0);
    }, 5000);
  });
}
