/**
 * Regression tests for the audio queue worker (processJob).
 * Mirrors the WorkerDefaultsRegressionTests from the original Python test suite.
 */

// --- Module mocks (hoisted before imports) ---
// Default-export mocks require __esModule: true so that esModuleInterop resolves
// `import X from 'module'` to the `.default` property, not the wrapper object.

jest.mock('../src/utils/config', () => ({
  __esModule: true,
  default: {
    OPENAI_API_KEY: 'sk-test',
    OPENAI_LLM_MODEL: 'oai-llm-test',
    OPENAI_TTS_MODEL: 'tts-1-hd',
    GOOGLE_API_KEY: 'g-test',
    GOOGLE_LLM_MODEL: 'google-llm-test',
    GOOGLE_TTS_MODEL: 'gemini-tts-test',
    LLM_PROVIDER: 'openai',
    TTS_PROVIDER: 'openai',
    ENV: 'test',
    LOG_LEVEL: 'silent',
    REDIS_CONNECTION: {},
    REDIS_DEFAULT_JOB_OPTIONS: {},
    S3_ENDPOINT_URL: 'http://localhost:9000',
    S3_PUBLIC_URL: '',
    S3_ACCESS_KEY_ID: 'test',
    S3_SECRET_ACCESS_KEY: 'test',
    S3_BUCKET_NAME: 'test-bucket',
  },
}));

jest.mock('../src/utils/logger', () => ({
  __esModule: true,
  default: { info: jest.fn(), warn: jest.fn(), error: jest.fn() },
}));

jest.mock('ioredis', () => ({
  __esModule: true,
  default: jest.fn().mockImplementation(() => ({
    on: jest.fn(),
    get: jest.fn(),
    set: jest.fn(),
    quit: jest.fn(),
  })),
}));

jest.mock('bullmq', () => ({
  Queue: jest.fn().mockImplementation(() => ({ add: jest.fn() })),
  Worker: jest.fn().mockImplementation(() => ({ on: jest.fn() })),
  Job: jest.fn(),
}));

jest.mock('../src/utils/jobStore', () => ({
  __esModule: true,
  default: {
    getJob: jest.fn(),
    updateJob: jest.fn(),
    createJob: jest.fn(),
  },
}));

jest.mock('../src/services/v1/audioServices/podcastService', () => ({
  __esModule: true,
  default: { generatePodcastAudio: jest.fn() },
}));
jest.mock('../src/services/v1/audioServices/narrationService', () => ({
  __esModule: true,
  default: { generateNarrationAudio: jest.fn() },
}));
jest.mock('../src/services/v1/audioServices/instagramService', () => ({
  __esModule: true,
  default: { generateInstagramAudio: jest.fn() },
}));
jest.mock('../src/services/v1/audioServices/notebooklmService', () => ({
  __esModule: true,
  default: { generateNotebooklmPodcast: jest.fn() },
}));

jest.mock('../src/services/v1/storageService', () => ({
  __esModule: true,
  default: { uploadAudio: jest.fn() },
}));
jest.mock('../src/services/v1/webhookService', () => ({
  __esModule: true,
  default: { fireWebhook: jest.fn() },
}));

jest.mock('../src/utils/audioUtils', () => ({
  __esModule: true,
  getMp3DurationSeconds: jest.fn(),
  pcmToMp3: jest.fn(),
  pcmChunksToMp3: jest.fn(),
  concatMp3Files: jest.fn(),
}));

jest.mock('../src/queues/addErrorHandlers', () => ({
  addWorkerErrorHandler: jest.fn(),
}));

// --- Imports (after mocks) ---

import { processJob } from '../src/queues/audioQueue';
import instagramService from '../src/services/v1/audioServices/instagramService';
import narrationService from '../src/services/v1/audioServices/narrationService';
import podcastService from '../src/services/v1/audioServices/podcastService';
import storageService from '../src/services/v1/storageService';
import { GenerateOptions, JobRecord } from '../src/tsTypes';
import { getMp3DurationSeconds } from '../src/utils/audioUtils';
import jobStore from '../src/utils/jobStore';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeJobRecord(
  type: JobRecord['type'],
  options: GenerateOptions = {}
): JobRecord {
  return {
    job_id: `job-${type}`,
    status: 'queued',
    type,
    content: '<p>Hello</p>',
    options,
    webhook_url: null,
    audio_url: null,
    duration_seconds: null,
    error: null,
    token_usage: null,
    created_at: new Date().toISOString(),
    tenant_id: null,
    content_type: null,
    content_id: null,
  };
}

// ---------------------------------------------------------------------------
// WorkerDefaultsRegressionTests
// ---------------------------------------------------------------------------

describe('WorkerDefaultsRegressionTests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (storageService.uploadAudio as jest.Mock).mockResolvedValue(
      'https://example.com/audio.mp3'
    );
    (getMp3DurationSeconds as jest.Mock).mockResolvedValue(12.3);
    (jobStore.updateJob as jest.Mock).mockResolvedValue(undefined);
  });

  test('podcast job: worker passes options through, service receives empty {}', async () => {
    const record = makeJobRecord('podcast');
    (jobStore.getJob as jest.Mock).mockResolvedValue(record);
    (podcastService.generatePodcastAudio as jest.Mock).mockResolvedValue({
      path: '/tmp/podcast.mp3',
      tokenUsage: {},
    });

    await processJob('job-podcast');

    expect(podcastService.generatePodcastAudio).toHaveBeenCalledWith(
      '<p>Hello</p>',
      {}
    );
    // word_count is undefined in options — resolved to default (600) inside the service
    const [, opts] = (podcastService.generatePodcastAudio as jest.Mock).mock
      .calls[0];
    expect(opts.word_count).toBeUndefined();
  });

  test('narration job: worker passes options through, service receives empty {}', async () => {
    const record = makeJobRecord('narration');
    (jobStore.getJob as jest.Mock).mockResolvedValue(record);
    (narrationService.generateNarrationAudio as jest.Mock).mockResolvedValue({
      path: '/tmp/narration.mp3',
      tokenUsage: {},
    });

    await processJob('job-narration');

    expect(narrationService.generateNarrationAudio).toHaveBeenCalledWith(
      '<p>Hello</p>',
      {}
    );
  });

  test('instagram job: google_tts_model override is passed through', async () => {
    const record = makeJobRecord('instagram', {
      google_tts_model: 'google-tts-override',
    });
    (jobStore.getJob as jest.Mock).mockResolvedValue(record);
    (instagramService.generateInstagramAudio as jest.Mock).mockResolvedValue({
      path: '/tmp/instagram.mp3',
      tokenUsage: {},
    });

    await processJob('job-instagram');

    const [, opts] = (instagramService.generateInstagramAudio as jest.Mock).mock
      .calls[0];
    expect(opts.google_tts_model).toBe('google-tts-override');
  });

  test('completed job is stored with audio_url and duration', async () => {
    const record = makeJobRecord('podcast');
    (jobStore.getJob as jest.Mock).mockResolvedValue(record);
    (podcastService.generatePodcastAudio as jest.Mock).mockResolvedValue({
      path: '/tmp/podcast.mp3',
      tokenUsage: {
        llm: { input_tokens: 5, output_tokens: 10, total_tokens: 15 },
      },
    });

    await processJob('job-podcast');

    const updateCalls = (jobStore.updateJob as jest.Mock).mock.calls;
    const completionCall = updateCalls.find(
      ([, u]: [string, { status?: string }]) => u.status === 'completed'
    );
    expect(completionCall).toBeDefined();
    expect(completionCall[1].audio_url).toBe('https://example.com/audio.mp3');
    expect(completionCall[1].duration_seconds).toBe(12.3);
  });

  test('job with missing content is failed immediately without calling service', async () => {
    const record: JobRecord = { ...makeJobRecord('podcast'), content: null };
    (jobStore.getJob as jest.Mock).mockResolvedValue(record);

    await processJob('job-no-content');

    const updateCalls = (jobStore.updateJob as jest.Mock).mock.calls;
    const failCall = updateCalls.find(
      ([, u]: [string, { status?: string }]) => u.status === 'failed'
    );
    expect(failCall[1].error).toBe('Missing content');
    expect(podcastService.generatePodcastAudio).not.toHaveBeenCalled();
  });
});
