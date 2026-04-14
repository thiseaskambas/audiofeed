import { GoogleGenAI } from '@google/genai';
import fs from 'fs';
import OpenAI from 'openai';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';

import { GenerateOptions, TokenUsage } from '../../../tsTypes';
import { pcmToMp3 } from '../../../utils/audioUtils';
import config from '../../../utils/config';
import { TMP_DIR } from '../../../utils/constants';
import { stripHtml, toBcp47 } from '../../../utils/htmlUtils';

const INSTAGRAM_SYSTEM =
  'You are a social media copywriter. Given an article, write a single punchy hook for an Instagram voiceover.\n' +
  '- Exactly around 60 words. One short paragraph.\n' +
  '- Engaging, conversational, hook the listener in 15–30 seconds.\n' +
  '- No markdown. Plain text only.';

const scriptOpenai = async (
  content: string,
  language: string
): Promise<{ script: string; usage: TokenUsage['llm'] }> => {
  const client = new OpenAI({ apiKey: config.OPENAI_API_KEY });
  const langInstruction =
    language === 'en' ? 'Write in English.' : `Write in ${language}.`;
  const resp = await client.chat.completions.create({
    model: config.OPENAI_LLM_MODEL,
    messages: [
      { role: 'system', content: `${INSTAGRAM_SYSTEM} ${langInstruction}` },
      { role: 'user', content: `Article:\n\n${content.slice(0, 8000)}` },
    ],
    max_tokens: 150,
  });
  return {
    script: (resp.choices[0].message.content ?? '').trim(),
    usage: {
      input_tokens: resp.usage?.prompt_tokens ?? null,
      output_tokens: resp.usage?.completion_tokens ?? null,
      total_tokens: resp.usage?.total_tokens ?? null,
    },
  };
};

const scriptGoogle = async (
  content: string,
  language: string,
  stylePrompt?: string
): Promise<{ script: string; usage: TokenUsage['llm'] }> => {
  const client = new GoogleGenAI({ apiKey: config.GOOGLE_API_KEY });
  const langInstruction =
    language === 'en' ? 'Write in English.' : `Write in ${language}.`;
  const styleInstruction = stylePrompt
    ? `\nDelivery style: ${stylePrompt}`
    : '';
  const prompt =
    `${INSTAGRAM_SYSTEM} ${langInstruction}${styleInstruction}\n\n` +
    `Article:\n\n${content.slice(0, 8000)}\n\nPunchy 60-word hook:`;
  const r = await client.models.generateContent({
    model: config.GOOGLE_LLM_MODEL,
    contents: prompt,
  });
  return {
    script: (r.text ?? '').trim(),
    usage: {
      input_tokens: r.usageMetadata?.promptTokenCount ?? null,
      output_tokens: r.usageMetadata?.candidatesTokenCount ?? null,
      total_tokens: r.usageMetadata?.totalTokenCount ?? null,
    },
  };
};

const ttsOpenai = async (
  script: string,
  outPath: string
): Promise<TokenUsage['tts']> => {
  const client = new OpenAI({ apiKey: config.OPENAI_API_KEY });
  const ttsInput = script.slice(0, 4096);
  const response = await client.audio.speech.create({
    model: config.OPENAI_TTS_MODEL,
    voice: 'nova', // Instagram always uses nova
    input: ttsInput,
  });
  const buffer = Buffer.from(await response.arrayBuffer());
  fs.writeFileSync(outPath, buffer);
  return {
    input_characters: ttsInput.length,
    input_tokens: null,
    output_tokens: null,
    total_tokens: null,
  };
};

const ttsGemini = async (
  script: string,
  outPath: string,
  language: string,
  voiceName: string,
  ttsModel: string
): Promise<TokenUsage['tts']> => {
  const client = new GoogleGenAI({ apiKey: config.GOOGLE_API_KEY });
  const langCode = toBcp47(language);
  const response = await client.models.generateContent({
    model: ttsModel,
    contents: script.slice(0, 4000),
    config: {
      responseModalities: ['AUDIO'],
      speechConfig: {
        languageCode: langCode,
        voiceConfig: {
          prebuiltVoiceConfig: { voiceName },
        },
      },
    },
  });
  const base64 =
    response.candidates?.[0]?.content?.parts?.[0]?.inlineData?.data ?? '';
  const pcmBuffer = Buffer.from(base64, 'base64');
  await pcmToMp3(pcmBuffer, outPath);
  return {
    input_tokens: response.usageMetadata?.promptTokenCount ?? null,
    output_tokens: response.usageMetadata?.candidatesTokenCount ?? null,
    total_tokens: response.usageMetadata?.totalTokenCount ?? null,
    input_characters: null,
  };
};

const generateInstagramAudio = async (
  content: string,
  opts: GenerateOptions
): Promise<{ path: string; tokenUsage: TokenUsage }> => {
  const plain = stripHtml(content);
  if (!plain.trim()) throw new Error('Content is empty after stripping HTML');

  fs.mkdirSync(TMP_DIR, { recursive: true });
  const outPath = path.join(TMP_DIR, `instagram_${uuidv4()}.mp3`);

  const language = opts.language ?? 'en';
  const googleVoice = opts.google_voice ?? 'Aoede';
  const googleTtsModel = opts.google_tts_model ?? config.GOOGLE_TTS_MODEL;

  let script: string;
  let llmUsage: TokenUsage['llm'];

  if (config.LLM_PROVIDER === 'openai') {
    ({ script, usage: llmUsage } = await scriptOpenai(plain, language));
  } else {
    ({ script, usage: llmUsage } = await scriptGoogle(
      plain,
      language,
      opts.tts_style_prompt
    ));
  }

  let ttsUsage: TokenUsage['tts'];

  if (config.TTS_PROVIDER === 'openai') {
    ttsUsage = await ttsOpenai(script, outPath);
  } else {
    ttsUsage = await ttsGemini(
      script,
      outPath,
      language,
      googleVoice,
      googleTtsModel
    );
  }

  return { path: outPath, tokenUsage: { llm: llmUsage, tts: ttsUsage } };
};

export { scriptOpenai as instagramScriptOpenai };
export default { generateInstagramAudio };
