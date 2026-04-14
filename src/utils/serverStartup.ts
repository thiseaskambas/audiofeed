import fs from 'fs';
import { Server } from 'http';

import config from './config';
import { TMP_DIR } from './constants';
import logger from './logger';
import redisClient from './redisClient';

export const startServer = async (server: Server): Promise<void> => {
  const needsOpenai =
    config.LLM_PROVIDER === 'openai' || config.TTS_PROVIDER === 'openai';
  const needsGoogle =
    config.LLM_PROVIDER === 'google' || config.TTS_PROVIDER === 'google';

  if (
    needsOpenai &&
    (!config.OPENAI_API_KEY || !config.OPENAI_API_KEY.startsWith('sk-'))
  ) {
    throw new Error('OPENAI_API_KEY must be set and start with "sk-"');
  }
  if (needsGoogle && !config.GOOGLE_API_KEY) {
    throw new Error('GOOGLE_API_KEY must be set');
  }

  await redisClient.ping();
  logger.info('Redis connection verified');

  fs.mkdirSync(TMP_DIR, { recursive: true });

  server.listen(config.PORT, () => {
    logger.info(`Audiofeed server listening on port ${config.PORT}`);
    logger.info(
      `LLM: ${config.LLM_PROVIDER} (${config.LLM_PROVIDER === 'openai' ? config.OPENAI_LLM_MODEL : config.GOOGLE_LLM_MODEL}) | ` +
        `TTS: ${config.TTS_PROVIDER} (${config.TTS_PROVIDER === 'openai' ? config.OPENAI_TTS_MODEL : config.GOOGLE_TTS_MODEL})`
    );
  });
};
