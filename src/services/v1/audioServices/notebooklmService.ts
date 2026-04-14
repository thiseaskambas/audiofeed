import axios from 'axios';
import fs from 'fs';
import { GoogleAuth } from 'google-auth-library';
import { pipeline } from 'stream/promises';

import { GenerateOptions, TokenUsage } from '../../../tsTypes';
import config from '../../../utils/config';
import {
  NOTEBOOKLM_DAILY_KEY_PREFIX,
  NOTEBOOKLM_MAX_POLLS,
  NOTEBOOKLM_POLL_INTERVAL_MS,
  TMP_DIR,
} from '../../../utils/constants';
import { stripHtml, toBcp47 } from '../../../utils/htmlUtils';
import logger from '../../../utils/logger';
import redisClient from '../../../utils/redisClient';

const BASE_URL = 'https://discoveryengine.googleapis.com/v1alpha';

const getAccessToken = async (): Promise<string> => {
  const auth = new GoogleAuth({
    scopes: ['https://www.googleapis.com/auth/cloud-platform'],
  });
  const client = await auth.getClient();
  const tokenResponse = await client.getAccessToken();
  if (!tokenResponse.token) {
    throw new Error('Could not obtain Google access token');
  }
  return tokenResponse.token;
};

const checkAndIncrementRateLimit = async (): Promise<void> => {
  const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD UTC
  const key = `${NOTEBOOKLM_DAILY_KEY_PREFIX}${today}`;
  const count = await redisClient.incr(key);
  await redisClient.expire(key, 90_000); // 25 hours
  if (count > config.NOTEBOOKLM_DAILY_LIMIT) {
    throw new Error(
      `NotebookLM daily quota exceeded (${count - 1}/${config.NOTEBOOKLM_DAILY_LIMIT} podcasts already generated today)`
    );
  }
};

const submitPodcastJob = async (
  text: string,
  languageBcp47: string,
  length: string,
  focus: string | undefined,
  token: string
): Promise<string> => {
  if (!config.NOTEBOOKLM_PROJECT_ID) {
    throw new Error(
      "NOTEBOOKLM_PROJECT_ID must be set to use type='notebooklm_podcast'"
    );
  }
  const url =
    `${BASE_URL}/projects/${config.NOTEBOOKLM_PROJECT_ID}` +
    `/locations/${config.NOTEBOOKLM_LOCATION}:generatePodcast`;

  const body: Record<string, unknown> = {
    contexts: [{ text }],
    length,
    language: languageBcp47,
  };
  if (focus) body.focus = focus;

  const resp = await axios.post(url, body, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    timeout: 30_000,
  });

  const operationName = resp.data?.name;
  if (!operationName) {
    throw new Error(
      `NotebookLM API did not return an operation name. Response: ${JSON.stringify(resp.data)}`
    );
  }
  return operationName as string;
};

const pollOperation = async (
  operationName: string,
  token: string
): Promise<void> => {
  const url = `${BASE_URL}/${operationName}`;

  for (let i = 0; i < NOTEBOOKLM_MAX_POLLS; i++) {
    if (i > 0) {
      await new Promise((r) => setTimeout(r, NOTEBOOKLM_POLL_INTERVAL_MS));
    }
    const resp = await axios.get(url, {
      headers: { Authorization: `Bearer ${token}` },
      timeout: 30_000,
    });
    if (resp.data.done) {
      if (resp.data.error) {
        throw new Error(
          `NotebookLM operation failed: ${resp.data.error.message ?? JSON.stringify(resp.data.error)}`
        );
      }
      return;
    }
  }

  throw new Error(
    `NotebookLM operation '${operationName}' did not complete within ${(NOTEBOOKLM_MAX_POLLS * NOTEBOOKLM_POLL_INTERVAL_MS) / 1000}s`
  );
};

const downloadAudio = async (
  operationName: string,
  token: string,
  outPath: string
): Promise<void> => {
  const url = `${BASE_URL}/${operationName}:download?alt=media`;
  const resp = await axios.get(url, {
    headers: { Authorization: `Bearer ${token}` },
    responseType: 'stream',
    timeout: 120_000,
    maxRedirects: 5,
  });
  await pipeline(
    resp.data as NodeJS.ReadableStream,
    fs.createWriteStream(outPath)
  );
};

const generateNotebooklmPodcast = async (
  content: string,
  opts: GenerateOptions,
  jobId: string
): Promise<{ path: string; tokenUsage: TokenUsage }> => {
  fs.mkdirSync(TMP_DIR, { recursive: true });
  const outPath = `${TMP_DIR}/notebooklm_${jobId}.mp3`;

  const text = stripHtml(content);
  const language = opts.language ?? 'en';
  const languageBcp47 = toBcp47(language);
  const length = opts.notebooklm_length ?? 'STANDARD';
  const focus = opts.notebooklm_focus;

  await checkAndIncrementRateLimit();

  const token = await getAccessToken();

  logger.info('Submitting NotebookLM podcast', {
    jobId,
    length,
    languageBcp47,
  });
  const operationName = await submitPodcastJob(
    text,
    languageBcp47,
    length,
    focus,
    token
  );
  logger.info('NotebookLM operation started', { operationName });

  await pollOperation(operationName, token);
  logger.info('NotebookLM operation completed', { operationName });

  await downloadAudio(operationName, token, outPath);

  return {
    path: outPath,
    tokenUsage: { notebooklm: { operation: operationName } },
  };
};

export default { generateNotebooklmPodcast };
