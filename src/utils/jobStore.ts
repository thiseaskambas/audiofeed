import { v4 as uuidv4 } from 'uuid';

import {
  AudioType,
  GenerateOptions,
  JobRecord,
  JobStatus,
  TokenUsage,
} from '../tsTypes';
import { JOB_KEY_PREFIX, JOB_TTL_SECONDS } from './constants';
import redisClient from './redisClient';

const key = (jobId: string) => `${JOB_KEY_PREFIX}${jobId}`;

const createJob = async (params: {
  type: AudioType;
  webhook_url?: string;
  options?: GenerateOptions;
  content?: string;
  tenant_id?: string;
  content_type?: string;
  content_id?: string;
}): Promise<string> => {
  const job_id = uuidv4();
  const record: JobRecord = {
    job_id,
    status: 'queued',
    type: params.type,
    audio_url: null,
    duration_seconds: null,
    error: null,
    token_usage: null,
    created_at: new Date().toISOString().replace('+00:00', 'Z'),
    webhook_url: params.webhook_url ?? null,
    options: params.options ?? {},
    content: params.content ?? null,
    tenant_id: params.tenant_id ?? null,
    content_type: params.content_type ?? null,
    content_id: params.content_id ?? null,
  };
  await redisClient.set(
    key(job_id),
    JSON.stringify(record),
    'EX',
    JOB_TTL_SECONDS
  );
  return job_id;
};

const getJob = async (jobId: string): Promise<JobRecord | null> => {
  const raw = await redisClient.get(key(jobId));
  return raw ? (JSON.parse(raw) as JobRecord) : null;
};

const updateJob = async (
  jobId: string,
  updates: {
    status?: JobStatus;
    audio_url?: string;
    duration_seconds?: number | null;
    error?: string;
    token_usage?: TokenUsage;
  }
): Promise<void> => {
  const job = await getJob(jobId);
  if (!job) return;
  const updated: JobRecord = { ...job, ...updates };
  await redisClient.set(
    key(jobId),
    JSON.stringify(updated),
    'EX',
    JOB_TTL_SECONDS
  );
};

export default { createJob, getJob, updateJob };
