# Token Usage Tracking

Every completed job exposes a `token_usage` field in the `GET /jobs/{id}` response and in webhook payloads. This allows you to track API consumption and estimate costs per generation.

## Response shape

```json
{
  "token_usage": {
    "llm": {
      "model": "gemini-2.5-flash",
      "input_tokens": 1842,
      "output_tokens": 312,
      "total_tokens": 2154
    },
    "tts": {
      "model": "gemini-2.5-flash-preview-tts",
      "input_tokens": 312,
      "output_tokens": 0,
      "total_tokens": 312,
      "input_characters": null
    }
  }
}
```

`token_usage` is present for all job types. See [Notes](#notes) for podcast-specific behaviour.

## Fields

### `llm`

Tokens consumed by the LLM call that generates the spoken script.

| Field | Type | Description |
|---|---|---|
| `model` | string \| null | Model identifier used for script generation (e.g. `gpt-4o-mini`, `gemini-2.5-flash`) |
| `input_tokens` | int | Prompt tokens sent to the model |
| `output_tokens` | int | Completion tokens returned by the model |
| `total_tokens` | int | Sum of input + output |

### `tts`

Tokens (or characters) consumed by the text-to-speech step.

| Field | Type | Description |
|---|---|---|
| `model` | string \| null | Model identifier used for TTS (e.g. `tts-1-hd`, `gemini-2.5-flash-preview-tts`) |
| `input_tokens` | int \| null | Tokens sent to the TTS model (Gemini only) |
| `output_tokens` | int \| null | Tokens returned by the TTS model (Gemini only) |
| `total_tokens` | int \| null | Sum of input + output (Gemini only) |
| `input_characters` | int \| null | Characters sent to TTS (OpenAI only — billed per character) |

## Provider behaviour

### OpenAI (`provider=openai`)

- **LLM** (`OPENAI_LLM_MODEL`): returns token counts via `response.usage`. `llm.model` is set to the configured model name (e.g. `gpt-4o-mini`).
- **TTS** (`OPENAI_TTS_MODEL`): billed per character, not per token. `tts.model` is set to the configured model name (e.g. `tts-1-hd`). `input_characters` is set; token fields are `null`.

### Google (`provider=google`)

- **LLM** (`GOOGLE_LLM_MODEL`): returns token counts via `response.usage_metadata`. `llm.model` is set to the configured model name (e.g. `gemini-2.5-flash`).
- **TTS** (`google_tts_model` request option or `GOOGLE_TTS_MODEL` env default): also returns token counts via `response.usage_metadata`. `tts.model` is set to the actual model used. `input_characters` is `null`.

## Job types

| Type | `token_usage` |
|---|---|
| `narration` | populated with `llm` + `tts` |
| `instagram` | populated with `llm` + `tts` |
| `podcast` | populated with `llm` + `tts` |
| `notebooklm_podcast` | `{ "notebooklm": { "operation": "<operation-name>" } }` — no token counts |

## Notes

### Podcast token usage

The `podcast` type runs its own LLM + TTS pipeline (no third-party library) and
returns full `token_usage` like the other types.

- `TTS_PROVIDER=google`: `tts` contains token counts from Gemini multi-speaker TTS.
  If the transcript is chunked, counts are summed across all chunks.
- `TTS_PROVIDER=openai`: `tts.input_characters` is the total characters sent across
  all per-turn TTS calls; token fields are `null`.

### Cost estimation

The `model` field is included so callers can price each generation accurately:

- **OpenAI TTS** (e.g. `tts-1-hd`): use `tts.input_characters` with per-character pricing.
  As of early 2026, `tts-1-hd` pricing is $30 / 1M characters.
- **Google TTS** (e.g. `gemini-2.5-flash-preview-tts`): use `tts.input_tokens` and
  `tts.output_tokens` with the token-based pricing for the specific model.
- **LLM** (script generation): use `llm.input_tokens` + `llm.output_tokens` with the
  per-token pricing for the model reported in `llm.model`.

### NotebookLM podcast

The `notebooklm_podcast` type bypasses the LLM and TTS steps entirely — generation happens inside Google's API. Token counts are not exposed by the NotebookLM API, so `token_usage` only contains the operation name for traceability:

```json
{
  "token_usage": {
    "notebooklm": {
      "operation": "projects/my-project/locations/global/operations/abc123"
    }
  }
}
```

Billing for NotebookLM Enterprise is managed through your Google Cloud contract — consult your Google account team for pricing details.
