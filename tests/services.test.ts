/**
 * Regression tests for audio service functions.
 * Mirrors the logic of the original Python test_regressions.py.
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
  },
}));

jest.mock('../src/utils/logger', () => ({
  __esModule: true,
  default: { info: jest.fn(), warn: jest.fn(), error: jest.fn() },
  requestLogger: jest.fn((_req: unknown, _res: unknown, next: () => void) =>
    next()
  ),
  errorLogger: jest.fn(
    (_err: unknown, _req: unknown, _res: unknown, next: () => void) => next()
  ),
}));

jest.mock('openai', () => ({
  __esModule: true,
  default: jest.fn(),
}));

jest.mock('@google/genai', () => ({
  // named export — no __esModule flag needed
  GoogleGenAI: jest.fn(),
}));

jest.mock('../src/utils/audioUtils', () => ({
  __esModule: true,
  pcmToMp3: jest.fn(),
  pcmChunksToMp3: jest.fn(),
  concatMp3Files: jest.fn(),
  getMp3DurationSeconds: jest.fn(),
}));

// --- Imports (after mocks) ---

import { GoogleGenAI } from '@google/genai';
import OpenAI from 'openai';

import { instagramScriptOpenai } from '../src/services/v1/audioServices/instagramService';
import { narrationScriptOpenai } from '../src/services/v1/audioServices/narrationService';
import {
  chunkTranscript,
  dialogGoogle,
  dialogOpenai,
} from '../src/services/v1/audioServices/podcastService';

// ---------------------------------------------------------------------------
// PodcastChunkTranscriptTests
// ---------------------------------------------------------------------------

describe('PodcastChunkTranscriptTests', () => {
  test('malformed transcript raises "No dialogue turns found"', () => {
    expect(() => chunkTranscript('No Host or Guest labels here.')).toThrow(
      'No dialogue turns found'
    );
  });

  test('valid transcript returns it as a single chunk', () => {
    const t = 'Host: One.\nGuest: Two.';
    expect(chunkTranscript(t)).toEqual([t]);
  });
});

// ---------------------------------------------------------------------------
// NarrationRegressionTests
// ---------------------------------------------------------------------------

describe('NarrationRegressionTests', () => {
  let mockCreate: jest.Mock;

  beforeEach(() => {
    mockCreate = jest.fn().mockResolvedValue({
      choices: [{ message: { content: 'Narration script' } }],
      usage: { prompt_tokens: 10, completion_tokens: 20, total_tokens: 30 },
    });
    (OpenAI as jest.Mock).mockImplementation(() => ({
      chat: { completions: { create: mockCreate } },
    }));
  });

  test('prompt includes requested word limit', async () => {
    const result = await narrationScriptOpenai('Article body', 'en', 123);
    expect(result.script).toBe('Narration script');
    expect(result.usage).toEqual({
      input_tokens: 10,
      output_tokens: 20,
      total_tokens: 30,
    });
    const systemMsg: string = mockCreate.mock.calls[0][0].messages[0].content;
    expect(systemMsg).toContain('123 words maximum');
    expect(mockCreate.mock.calls[0][0].model).toBe('oai-llm-test');
  });
});

// ---------------------------------------------------------------------------
// InstagramRegressionTests
// ---------------------------------------------------------------------------

describe('InstagramRegressionTests', () => {
  let mockCreate: jest.Mock;

  beforeEach(() => {
    mockCreate = jest.fn().mockResolvedValue({
      choices: [{ message: { content: 'Hook text' } }],
      usage: null,
    });
    (OpenAI as jest.Mock).mockImplementation(() => ({
      chat: { completions: { create: mockCreate } },
    }));
  });

  test('handles missing usage (null) gracefully', async () => {
    const result = await instagramScriptOpenai('Article body', 'en');
    expect(result.script).toBe('Hook text');
    expect(result.usage).toEqual({
      input_tokens: null,
      output_tokens: null,
      total_tokens: null,
    });
    expect(mockCreate.mock.calls[0][0].model).toBe('oai-llm-test');
  });
});

// ---------------------------------------------------------------------------
// PodcastDialogInstructionsTests
// ---------------------------------------------------------------------------

describe('PodcastDialogInstructionsTests — OpenAI', () => {
  let mockCreate: jest.Mock;

  beforeEach(() => {
    mockCreate = jest.fn().mockResolvedValue({
      choices: [{ message: { content: 'Host: Hi.\nGuest: Hey.' } }],
      usage: { prompt_tokens: 1, completion_tokens: 2, total_tokens: 3 },
    });
    (OpenAI as jest.Mock).mockImplementation(() => ({
      chat: { completions: { create: mockCreate } },
    }));
  });

  test('instructions appended to system prompt', async () => {
    const result = await dialogOpenai(
      'Article body',
      'en',
      400,
      'educational',
      'Host is Alex. Guest is Sam.'
    );
    expect(result.transcript).toBe('Host: Hi.\nGuest: Hey.');
    expect(result.usage?.total_tokens).toBe(3);
    const systemMsg: string = mockCreate.mock.calls[0][0].messages[0].content;
    expect(systemMsg).toContain('Additional instructions:');
    expect(systemMsg).toContain('Host is Alex. Guest is Sam.');
  });

  test('no "Additional instructions:" block when instructions is undefined', async () => {
    await dialogOpenai('Body', 'en', 100, 'fast');
    const systemMsg: string = mockCreate.mock.calls[0][0].messages[0].content;
    expect(systemMsg).not.toContain('Additional instructions:');
  });

  test('max_tokens uses expanded formula: word_count * 3 (capped at 8000)', async () => {
    await dialogOpenai('Article body', 'en', 600, 'educational');
    expect(mockCreate.mock.calls[0][0].max_tokens).toBe(1800); // 600 * 3
  });
});

describe('PodcastDialogInstructionsTests — Google', () => {
  let mockGenerateContent: jest.Mock;

  beforeEach(() => {
    mockGenerateContent = jest.fn().mockResolvedValue({
      text: 'Host: A.\nGuest: B.',
      usageMetadata: {
        promptTokenCount: 10,
        candidatesTokenCount: 5,
        totalTokenCount: 15,
      },
    });
    (GoogleGenAI as jest.Mock).mockImplementation(() => ({
      models: { generateContent: mockGenerateContent },
    }));
  });

  test('instructions appended before article in prompt', async () => {
    const result = await dialogGoogle(
      'Art text',
      'en',
      200,
      'calm',
      'Use names from the briefing.'
    );
    expect(result.transcript).toBe('Host: A.\nGuest: B.');
    expect(result.usage?.total_tokens).toBe(15);
    const prompt: string = mockGenerateContent.mock.calls[0][0].contents;
    expect(prompt).toContain('Additional instructions:');
    expect(prompt).toContain('Use names from the briefing.');
    expect(prompt).toContain(
      'Use names from the briefing.\n\nArticle:\n\nArt text'
    );
    expect(mockGenerateContent.mock.calls[0][0].model).toBe('google-llm-test');
  });
});
