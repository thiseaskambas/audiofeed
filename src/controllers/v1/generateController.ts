import { Request, Response } from 'express';

import { audioQueue } from '../../queues/audioQueue';
import { AudioType, ErrorStatusCode, GenerateRequestBody } from '../../tsTypes';
import { AppError } from '../../utils/appError';
import { catchAsync } from '../../utils/catchAsync';
import config from '../../utils/config';
import jobStore from '../../utils/jobStore';

const VALID_TYPES: AudioType[] = [
  'podcast',
  'narration',
  'instagram',
  'notebooklm_podcast',
];

const generate = catchAsync(async (req: Request, res: Response) => {
  const body = req.body as GenerateRequestBody;

  if (!body.type || !body.content) {
    throw new AppError({
      message: 'type and content are required',
      statusCode: ErrorStatusCode.BAD_REQUEST,
    });
  }
  if (!VALID_TYPES.includes(body.type)) {
    throw new AppError({
      message: `type must be one of: ${VALID_TYPES.join(', ')}`,
      statusCode: ErrorStatusCode.BAD_REQUEST,
    });
  }

  const jobId = await jobStore.createJob({
    type: body.type,
    webhook_url: body.webhook_url,
    options: body.options,
    content: body.content,
    tenant_id: body.tenant_id,
    content_type: body.content_type,
    content_id: body.content_id,
  });

  await audioQueue.add('run-job', { jobId });

  res.status(202).json({ job_id: jobId, status: 'queued' });
});

const getJobStatus = catchAsync(async (req: Request, res: Response) => {
  const rawJobId = req.params.jobId;
  const jobId = Array.isArray(rawJobId) ? rawJobId[0] : rawJobId;
  if (!jobId) {
    throw new AppError({
      message: 'Job id is required',
      statusCode: ErrorStatusCode.BAD_REQUEST,
    });
  }
  const job = await jobStore.getJob(jobId);
  if (!job) {
    throw new AppError({
      message: 'Job not found',
      statusCode: ErrorStatusCode.NOT_FOUND,
    });
  }
  const { content: _c, options: _o, webhook_url: _w, ...publicFields } = job;
  res.status(200).json(publicFields);
});

const health = (_req: Request, res: Response): void => {
  res.status(200).json({
    status: 'healthy',
    llm_provider: config.LLM_PROVIDER,
    tts_provider: config.TTS_PROVIDER,
  });
};

export default { generate, getJobStatus, health };
