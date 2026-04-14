export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed';
export type AudioType =
  | 'podcast'
  | 'narration'
  | 'instagram'
  | 'notebooklm_podcast';
export type LlmProvider = 'openai' | 'google';

export interface TokenUsageLlm {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
}

export interface TokenUsageTts {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  input_characters: number | null;
}

export interface TokenUsage {
  llm?: TokenUsageLlm;
  tts?: TokenUsageTts;
  notebooklm?: { operation: string };
}

export interface GenerateOptions {
  language?: string;
  voice?: string;
  word_count?: number;
  style?: string;
  google_voice?: string;
  google_tts_model?: string;
  tts_style_prompt?: string;
  podcast_voice1?: string;
  podcast_voice2?: string;
  podcast_openai_voice1?: string;
  podcast_openai_voice2?: string;
  podcast_instructions?: string;
  notebooklm_length?: 'SHORT' | 'STANDARD';
  notebooklm_focus?: string;
}

export interface JobRecord {
  job_id: string;
  status: JobStatus;
  type: AudioType;
  audio_url: string | null;
  duration_seconds: number | null;
  error: string | null;
  token_usage: TokenUsage | null;
  created_at: string;
  webhook_url: string | null;
  options: GenerateOptions;
  content: string | null;
  tenant_id: string | null;
  content_type: string | null;
  content_id: string | null;
}

export interface GenerateRequestBody {
  type: AudioType;
  content: string;
  webhook_url?: string;
  options?: GenerateOptions;
  tenant_id?: string;
  content_type?: string;
  content_id?: string;
}
