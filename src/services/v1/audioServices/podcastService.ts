import { GoogleGenAI } from '@google/genai';
import fs from 'fs';
import OpenAI from 'openai';
import os from 'os';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';

import { GenerateOptions, TokenUsage } from '../../../tsTypes';
import { concatMp3Files, pcmChunksToMp3 } from '../../../utils/audioUtils';
import config from '../../../utils/config';
import { TMP_DIR } from '../../../utils/constants';
import { stripHtml, toBcp47 } from '../../../utils/htmlUtils';

const DIALOG_SYSTEM =
  'You are a podcast scriptwriter. Given an article, write a natural two-person podcast dialogue.\n\n' +
  'Speaker roles:\n' +
  '- Host: a curious, enthusiastic interviewer. Asks questions, reacts with surprise or delight, keeps the conversation moving.\n' +
  '- Guest: a knowledgeable, articulate explainer. Digs into detail, gives examples, occasionally qualifies or corrects themselves.\n\n' +
  'Naturalness rules — these are mandatory, not optional:\n' +
  '- Include disfluencies: um, uh, you know, I mean, like, kind of, sort of, actually, basically.\n' +
  '- Include back-channel responses on their own turn: "Right.", "Exactly.", "Yeah, totally.", "Mm-hmm.", "That makes sense.", "Fascinating.", "No kidding."\n' +
  '- Include false starts and self-corrections: "It\'s basically—well, it\'s more nuanced than that."\n' +
  '- Include genuine reactions: "Wait, really?", "Oh, that\'s interesting.", "Huh, I hadn\'t thought of that.", "Wow.", "That\'s wild."\n' +
  '- Vary turn lengths naturally: short punchy reactions (1-2 sentences) mixed with longer explanations (4-6 sentences).\n' +
  "- Use contractions throughout: it's, that's, we're, isn't, can't, don't, I've, you'd.\n\n" +
  'Structure:\n' +
  '1. Warm, natural intro where Host sets up the topic casually (not formally).\n' +
  '2. Main discussion broken into 3-5 natural topic segments with back-and-forth.\n' +
  '3. Brief, conversational conclusion — no formal sign-offs.\n\n' +
  'Format rules (strict — the audio pipeline depends on these):\n' +
  '- Every line must start with exactly "Host: " or "Guest: " (word, colon, space, then speech).\n' +
  '- No stage directions, no markdown, no bullet points, no blank lines between turns.\n' +
  '- Do not include any line that does not start with "Host: " or "Guest: ".\n' +
  '- Write entirely in the language of the article unless instructed otherwise.';

const chunkTranscript = (transcript: string, maxChars = 3000): string[] => {
  const lines = transcript
    .split('\n')
    .filter(
      (l) => l.trim().startsWith('Host: ') || l.trim().startsWith('Guest: ')
    );
  const chunks: string[] = [];
  const currentLines: string[] = [];
  let currentLen = 0;

  for (const line of lines) {
    if (currentLen + line.length + 1 > maxChars && currentLines.length > 0) {
      chunks.push(currentLines.join('\n'));
      currentLines.length = 0;
      currentLen = 0;
    }
    currentLines.push(line);
    currentLen += line.length + 1;
  }
  if (currentLines.length > 0) chunks.push(currentLines.join('\n'));
  if (chunks.length === 0) {
    throw new Error(
      "No dialogue turns found in transcript — expected lines starting with 'Host: ' or 'Guest: '"
    );
  }
  return chunks;
};

const dialogOpenai = async (
  content: string,
  language: string,
  wordCount: number,
  style: string,
  instructions?: string
): Promise<{ transcript: string; usage: TokenUsage['llm'] }> => {
  const client = new OpenAI({ apiKey: config.OPENAI_API_KEY });
  const langInstruction =
    language === 'en' ? 'Write in English.' : `Write in ${language}.`;
  let systemContent = `${DIALOG_SYSTEM} ${langInstruction} Style: ${style}. Target length: ${wordCount} words.`;
  if (instructions)
    systemContent += `\n\nAdditional instructions:\n${instructions}`;

  const resp = await client.chat.completions.create({
    model: config.OPENAI_LLM_MODEL,
    messages: [
      { role: 'system', content: systemContent },
      { role: 'user', content: `Article:\n\n${content.slice(0, 15000)}` },
    ],
    max_tokens: Math.min(wordCount * 3, 8000),
  });
  return {
    transcript: (resp.choices[0].message.content ?? '').trim(),
    usage: {
      model: config.OPENAI_LLM_MODEL,
      input_tokens: resp.usage?.prompt_tokens ?? null,
      output_tokens: resp.usage?.completion_tokens ?? null,
      total_tokens: resp.usage?.total_tokens ?? null,
    },
  };
};

const dialogGoogle = async (
  content: string,
  language: string,
  wordCount: number,
  style: string,
  instructions?: string
): Promise<{ transcript: string; usage: TokenUsage['llm'] }> => {
  const client = new GoogleGenAI({ apiKey: config.GOOGLE_API_KEY });
  const langInstruction =
    language === 'en' ? 'Write in English.' : `Write in ${language}.`;
  let prompt = `${DIALOG_SYSTEM} ${langInstruction} Style: ${style}. Target length: ${wordCount} words.`;
  if (instructions) prompt += `\n\nAdditional instructions:\n${instructions}`;
  prompt += `\n\nArticle:\n\n${content.slice(0, 15000)}\n\nDialogue:`;

  const r = await client.models.generateContent({
    model: config.GOOGLE_LLM_MODEL,
    contents: prompt,
    config: {
      thinkingConfig: { thinkingBudget: 0 },
    },
  });
  return {
    transcript: (r.text ?? '').trim(),
    usage: {
      model: config.GOOGLE_LLM_MODEL,
      input_tokens: r.usageMetadata?.promptTokenCount ?? null,
      output_tokens: r.usageMetadata?.candidatesTokenCount ?? null,
      total_tokens: r.usageMetadata?.totalTokenCount ?? null,
    },
  };
};

const ttsGeminiMultispeaker = async (
  transcript: string,
  outPath: string,
  voice1: string,
  voice2: string,
  ttsModel: string,
  language: string
): Promise<TokenUsage['tts']> => {
  const client = new GoogleGenAI({ apiKey: config.GOOGLE_API_KEY });
  const langCode = toBcp47(language);

  const ttsConfig = {
    responseModalities: ['AUDIO' as const],
    speechConfig: {
      languageCode: langCode,
      multiSpeakerVoiceConfig: {
        speakerVoiceConfigs: [
          {
            speaker: 'Host',
            voiceConfig: { prebuiltVoiceConfig: { voiceName: voice1 } },
          },
          {
            speaker: 'Guest',
            voiceConfig: { prebuiltVoiceConfig: { voiceName: voice2 } },
          },
        ],
      },
    },
  };

  const chunks = chunkTranscript(transcript, 3000);
  const pcmChunks: Buffer[] = [];
  let totalInput = 0;
  let totalOutput = 0;
  let totalTokens = 0;

  for (const chunk of chunks) {
    const response = await client.models.generateContent({
      model: ttsModel,
      contents: chunk,
      config: ttsConfig,
    });
    const base64 =
      response.candidates?.[0]?.content?.parts?.[0]?.inlineData?.data ?? '';
    pcmChunks.push(Buffer.from(base64, 'base64'));
    if (response.usageMetadata) {
      totalInput += response.usageMetadata.promptTokenCount ?? 0;
      totalOutput += response.usageMetadata.candidatesTokenCount ?? 0;
      totalTokens += response.usageMetadata.totalTokenCount ?? 0;
    }
  }

  await pcmChunksToMp3(pcmChunks, outPath);

  return {
    model: ttsModel,
    input_tokens: totalInput || null,
    output_tokens: totalOutput || null,
    total_tokens: totalTokens || null,
    input_characters: null,
  };
};

const ttsOpenaiTurns = async (
  transcript: string,
  outPath: string,
  voice1: string,
  voice2: string
): Promise<TokenUsage['tts']> => {
  const client = new OpenAI({ apiKey: config.OPENAI_API_KEY });
  const tmpFiles: string[] = [];
  let totalChars = 0;

  for (const line of transcript.split('\n')) {
    const trimmed = line.trim();
    let voice: string;
    let text: string;

    if (trimmed.startsWith('Host: ')) {
      voice = voice1;
      text = trimmed.slice(6);
    } else if (trimmed.startsWith('Guest: ')) {
      voice = voice2;
      text = trimmed.slice(7);
    } else {
      continue;
    }
    if (!text.trim()) continue;

    totalChars += text.length;
    const ttsInput = text.slice(0, 4096);
    const response = await client.audio.speech.create({
      model: config.OPENAI_TTS_MODEL,
      voice: voice as Parameters<typeof client.audio.speech.create>[0]['voice'],
      input: ttsInput,
    });
    const buffer = Buffer.from(await response.arrayBuffer());
    const tmpPath = path.join(os.tmpdir(), `turn_${uuidv4()}.mp3`);
    fs.writeFileSync(tmpPath, buffer);
    tmpFiles.push(tmpPath);
  }

  if (tmpFiles.length === 0) {
    throw new Error('No dialogue turns found in transcript');
  }

  await concatMp3Files(tmpFiles, outPath);

  // Clean up temp turn files
  for (const f of tmpFiles) {
    fs.unlink(f, () => undefined);
  }

  return {
    model: config.OPENAI_TTS_MODEL,
    input_characters: totalChars,
    input_tokens: null,
    output_tokens: null,
    total_tokens: null,
  };
};

const generatePodcastAudio = async (
  content: string,
  opts: GenerateOptions
): Promise<{ path: string; tokenUsage: TokenUsage }> => {
  const plain = stripHtml(content);
  if (!plain.trim()) throw new Error('Content is empty after stripping HTML');

  fs.mkdirSync(TMP_DIR, { recursive: true });
  const outPath = path.join(TMP_DIR, `podcast_${uuidv4()}.mp3`);

  const language = opts.language ?? 'en';
  const wordCount = opts.word_count ?? 600;
  const style = opts.style ?? 'engaging,fast-paced';
  const voice1 = opts.podcast_voice1 ?? 'Puck';
  const voice2 = opts.podcast_voice2 ?? 'Charon';
  const openaiVoice1 = opts.podcast_openai_voice1 ?? 'alloy';
  const openaiVoice2 = opts.podcast_openai_voice2 ?? 'echo';
  const googleTtsModel = opts.google_tts_model ?? config.GOOGLE_TTS_MODEL;

  let transcript: string;
  let llmUsage: TokenUsage['llm'];

  if (config.LLM_PROVIDER === 'openai') {
    ({ transcript, usage: llmUsage } = await dialogOpenai(
      plain,
      language,
      wordCount,
      style,
      opts.podcast_instructions
    ));
  } else {
    ({ transcript, usage: llmUsage } = await dialogGoogle(
      plain,
      language,
      wordCount,
      style,
      opts.podcast_instructions
    ));
  }

  if (!transcript.trim()) throw new Error('LLM returned an empty transcript');

  let ttsUsage: TokenUsage['tts'];

  if (config.TTS_PROVIDER === 'google') {
    ttsUsage = await ttsGeminiMultispeaker(
      transcript,
      outPath,
      voice1,
      voice2,
      googleTtsModel,
      language
    );
  } else {
    ttsUsage = await ttsOpenaiTurns(
      transcript,
      outPath,
      openaiVoice1,
      openaiVoice2
    );
  }

  return { path: outPath, tokenUsage: { llm: llmUsage, tts: ttsUsage } };
};

export { chunkTranscript, dialogGoogle, dialogOpenai };
export default { generatePodcastAudio };
