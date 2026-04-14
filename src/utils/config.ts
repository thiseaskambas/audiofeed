import * as dotenv from 'dotenv';

import {
  parseOptionalString,
  parsePort,
  parseProvider,
  parseString,
} from '../tsParsers';
import { LlmProvider } from '../tsTypes';

dotenv.config();

const PORT: number = parsePort(process.env.PORT);
const ENV: string = process.env.ENV?.trim() || 'DEV';
const LOG_LEVEL: string = process.env.LOG_LEVEL?.trim() || 'info';

const LLM_PROVIDER: LlmProvider = parseProvider(process.env.LLM_PROVIDER);
const TTS_PROVIDER: LlmProvider = parseProvider(process.env.TTS_PROVIDER);

const OPENAI_API_KEY: string | undefined = parseOptionalString(
  process.env.OPENAI_API_KEY
);
const OPENAI_LLM_MODEL: string =
  process.env.OPENAI_LLM_MODEL?.trim() || 'gpt-4o-mini';
const OPENAI_TTS_MODEL: string =
  process.env.OPENAI_TTS_MODEL?.trim() || 'tts-1-hd';

const GOOGLE_API_KEY: string | undefined = parseOptionalString(
  process.env.GOOGLE_API_KEY
);
const GOOGLE_LLM_MODEL: string =
  process.env.GOOGLE_LLM_MODEL?.trim() || 'gemini-2.5-flash';
const GOOGLE_TTS_MODEL: string =
  process.env.GOOGLE_TTS_MODEL?.trim() || 'gemini-2.5-flash-preview-tts';

const NOTEBOOKLM_PROJECT_ID: string | undefined = parseOptionalString(
  process.env.NOTEBOOKLM_PROJECT_ID
);
const NOTEBOOKLM_LOCATION: string =
  process.env.NOTEBOOKLM_LOCATION?.trim() || 'global';
const NOTEBOOKLM_DAILY_LIMIT: number = parseInt(
  process.env.NOTEBOOKLM_DAILY_LIMIT || '20',
  10
);

const S3_ENDPOINT_URL: string = parseString(
  process.env.S3_ENDPOINT_URL,
  'S3_ENDPOINT_URL'
);
const S3_PUBLIC_URL: string = process.env.S3_PUBLIC_URL?.trim() || '';
const S3_ACCESS_KEY_ID: string = parseString(
  process.env.S3_ACCESS_KEY_ID,
  'S3_ACCESS_KEY_ID'
);
const S3_SECRET_ACCESS_KEY: string = parseString(
  process.env.S3_SECRET_ACCESS_KEY,
  'S3_SECRET_ACCESS_KEY'
);
const S3_BUCKET_NAME: string =
  process.env.S3_BUCKET_NAME?.trim() || 'audiofeed-audio';

const API_SECRET: string = parseString(process.env.API_SECRET, 'API_SECRET');

// Note: Python uses REDIS_URL — keep env var name the same for .env compatibility
const REDIS_URI: string = parseString(process.env.REDIS_URL, 'REDIS_URL');
const redisUrl = new URL(REDIS_URI);
const REDIS_HOST: string = redisUrl.hostname;
const REDIS_PORT: number = parseInt(redisUrl.port || '6379', 10);
const REDIS_PASSWORD: string = redisUrl.password || '';
const REDIS_TLS = redisUrl.protocol === 'rediss:' ? {} : undefined;
const REDIS_CONNECTION = {
  host: REDIS_HOST,
  port: REDIS_PORT,
  ...(REDIS_PASSWORD && { password: REDIS_PASSWORD }),
  ...(REDIS_TLS !== undefined && { tls: REDIS_TLS }),
  maxRetriesPerRequest: null as null,
  enableOfflineQueue: true,
  retryStrategy: (times: number) => Math.min(times * 50, 2000),
};
const REDIS_DEFAULT_JOB_OPTIONS = {
  removeOnComplete: {
    age: 3600,
    count: 1000,
  },
  removeOnFail: {
    age: 24 * 3600,
  },
  lockDuration: 1000 * 60 * 20,
};

export default {
  PORT,
  ENV,
  LOG_LEVEL,
  LLM_PROVIDER,
  TTS_PROVIDER,
  OPENAI_API_KEY,
  OPENAI_LLM_MODEL,
  OPENAI_TTS_MODEL,
  GOOGLE_API_KEY,
  GOOGLE_LLM_MODEL,
  GOOGLE_TTS_MODEL,
  NOTEBOOKLM_PROJECT_ID,
  NOTEBOOKLM_LOCATION,
  NOTEBOOKLM_DAILY_LIMIT,
  S3_ENDPOINT_URL,
  S3_PUBLIC_URL,
  S3_ACCESS_KEY_ID,
  S3_SECRET_ACCESS_KEY,
  S3_BUCKET_NAME,
  API_SECRET,
  REDIS_CONNECTION,
  REDIS_DEFAULT_JOB_OPTIONS,
};
