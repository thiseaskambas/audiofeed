import path from 'path';

export const JOB_TTL_SECONDS = 86_400; // 24h
export const JOB_KEY_PREFIX = 'job:';
export const NOTEBOOKLM_POLL_INTERVAL_MS = 10_000;
export const NOTEBOOKLM_MAX_POLLS = 60;
export const NOTEBOOKLM_DAILY_KEY_PREFIX = 'notebooklm:daily_usage:';
export const TMP_DIR = path.join(process.cwd(), 'data', 'audio', 'tmp');
export const AUDIO_S3_PREFIX = 'audiofeed';
