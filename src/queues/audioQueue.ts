import { Job, Queue, Worker } from 'bullmq';
import fs from 'fs';

import instagramService from '../services/v1/audioServices/instagramService';
import narrationService from '../services/v1/audioServices/narrationService';
import notebooklmService from '../services/v1/audioServices/notebooklmService';
import podcastService from '../services/v1/audioServices/podcastService';
import storageService from '../services/v1/storageService';
import webhookService from '../services/v1/webhookService';
import { JobRecord, TokenUsage } from '../tsTypes';
import { getMp3DurationSeconds } from '../utils/audioUtils';
import config from '../utils/config';
import jobStore from '../utils/jobStore';
import logger from '../utils/logger';
import { addWorkerErrorHandler } from './addErrorHandlers';

interface AudioJobData {
  jobId: string;
}

export const audioQueue = new Queue('audioQueue', {
  connection: config.REDIS_CONNECTION,
  defaultJobOptions: config.REDIS_DEFAULT_JOB_OPTIONS,
});

const maybeWebhook = async (
  job: JobRecord,
  webhookUrl: string | null
): Promise<void> => {
  if (!webhookUrl) return;
  const final = await jobStore.getJob(job.job_id);
  if (!final) return;
  const { content: _c, options: _o, webhook_url: _w, ...publicFields } = final;
  await webhookService.fireWebhook(
    webhookUrl,
    publicFields as unknown as Record<string, unknown>
  );
};

export const processJob = async (jobId: string): Promise<void> => {
  const record = await jobStore.getJob(jobId);

  if (!record || record.status !== 'queued') return;

  await jobStore.updateJob(jobId, { status: 'processing' });

  const opts = record.options ?? {};
  const content = record.content;

  if (!content) {
    await jobStore.updateJob(jobId, {
      status: 'failed',
      error: 'Missing content',
    });
    await maybeWebhook(record, record.webhook_url);
    return;
  }

  try {
    let audioPath: string;
    let tokenUsage: TokenUsage;
    let prefix: string;

    if (record.type === 'podcast') {
      ({ path: audioPath, tokenUsage } =
        await podcastService.generatePodcastAudio(content, opts));
      prefix = 'podcast';
    } else if (record.type === 'narration') {
      ({ path: audioPath, tokenUsage } =
        await narrationService.generateNarrationAudio(content, opts));
      prefix = 'narration';
    } else if (record.type === 'instagram') {
      ({ path: audioPath, tokenUsage } =
        await instagramService.generateInstagramAudio(content, opts));
      prefix = 'instagram';
    } else if (record.type === 'notebooklm_podcast') {
      ({ path: audioPath, tokenUsage } =
        await notebooklmService.generateNotebooklmPodcast(
          content,
          opts,
          jobId
        ));
      prefix = 'notebooklm_podcast';
    } else {
      await jobStore.updateJob(jobId, {
        status: 'failed',
        error: `Unknown type: ${record.type}`,
      });
      await maybeWebhook(record, record.webhook_url);
      return;
    }

    const keyPrefix = record.tenant_id
      ? `${record.tenant_id}/${prefix}`
      : prefix;
    const audioUrl = await storageService.uploadAudio(audioPath, keyPrefix);
    const duration = await getMp3DurationSeconds(audioPath);

    fs.unlink(audioPath, () => undefined);

    await jobStore.updateJob(jobId, {
      status: 'completed',
      audio_url: audioUrl,
      duration_seconds: duration,
      token_usage: tokenUsage,
    });
    await maybeWebhook(record, record.webhook_url);
  } catch (err) {
    logger.error('Job failed', { jobId, err });
    await jobStore.updateJob(jobId, {
      status: 'failed',
      error: err instanceof Error ? err.message : String(err),
    });
    await maybeWebhook(record, record.webhook_url);
  }
};

const audioWorker = new Worker(
  'audioQueue',
  async (job: Job<AudioJobData>) => {
    await processJob(job.data.jobId);
  },
  { connection: config.REDIS_CONNECTION }
);

addWorkerErrorHandler(audioWorker, 'audioWorker');

export { audioWorker };
