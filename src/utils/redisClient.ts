import Redis from 'ioredis';

import config from './config';
import logger from './logger';

const redisClient = new Redis(config.REDIS_CONNECTION);

redisClient.on('error', (err) => logger.error('Redis client error', { err }));

export const closeRedis = () => redisClient.quit();

export default redisClient;
