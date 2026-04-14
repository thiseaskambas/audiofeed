import { createServer } from 'http';

import { app } from './src/app';
import { WORKERS_ARRAY } from './src/queues';
import { trackConnections } from './src/utils/gracefulShutdown';
import { setupProcessHandlers } from './src/utils/processHandlers';
import { startServer } from './src/utils/serverStartup';

async function main() {
  const server = createServer(app);
  trackConnections(server);
  setupProcessHandlers(server, WORKERS_ARRAY);
  await startServer(server);
}

main().catch((err) => {
  console.error('Failed to start server:', err);
  process.exit(1);
});
