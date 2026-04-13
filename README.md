# Audiofeed

Python REST microservice that turns article content (HTML or plain text) into audio. Supports four output types: **podcast** (two-speaker dialogue), **narration** (single speaker), **Instagram voiceover** (punchy ~60-word hook), and **NotebookLM podcast** (end-to-end generation via Google's NotebookLM Enterprise API). Jobs are processed asynchronously; results are uploaded to S3 and optionally delivered via webhook.

## Stack

| Concern | Technology |
|---|---|
| Framework | FastAPI |
| Job queue | ARQ + Redis (worker runs in-process) |
| LLM (scripts & dialogue) | OpenAI `gpt-4o-mini` or Google `gemini-2.5-flash` |
| TTS | OpenAI `tts-1-hd` or Google Gemini TTS (`gemini-2.5-flash-preview-tts`) |
| Podcast TTS | Google Gemini multi-speaker TTS (single API call, two voices) |
| NotebookLM podcast | Google NotebookLM Enterprise API (end-to-end, no LLM/TTS steps) |
| Storage | boto3 → Sevalla S3 |
| Auth | `X-API-Key` header (shared secret) |

---

## Architecture overview

```
POST /generate
      │
      ▼
  create_job()          ← Redis hash  job:{uuid}
  enqueue run_job()     ← ARQ queue
      │
      ▼ (ARQ worker, runs in same process)
  run_job(job_id)
      │
      ├─ type=podcast  ──────────► podcast.generate_podcast_audio()
      │                                │
      │                           1. strip HTML
      │                           2. LLM writes Host:/Guest: dialogue
      │                           3. Gemini multi-speaker TTS → PCM → MP3
      │
      ├─ type=narration ─────────► narration.generate_narration_audio()
      │                                │
      │                           1. strip HTML
      │                           2. LLM writes spoken script
      │                           3. TTS → MP3
      │
      ├─ type=instagram ─────────► instagram.generate_instagram_audio()
      │                                │
      │                           1. strip HTML
      │                           2. LLM writes ~60-word hook
      │                           3. TTS → MP3
      │
      └─ type=notebooklm_podcast ─► notebooklm.generate_notebooklm_podcast()
                                       │
                                  1. strip HTML
                                  2. POST to NotebookLM Enterprise API
                                  3. poll long-running operation (~10s intervals)
                                  4. download finished MP3
      │
      ▼
  upload to S3
  update job: status=completed, audio_url, duration_seconds, token_usage
  POST webhook_url (if provided)
```

---

## Project structure

```
app/
├── main.py              # FastAPI app + lifespan: startup validation, Redis init, ARQ worker
├── config.py            # Pydantic settings loaded from .env
├── jobs.py              # Redis-backed job store (create / get / update)
├── worker.py            # ARQ worker function run_job()
├── routes/
│   └── generate.py      # POST /generate  GET /jobs/{id}  GET /health
└── services/
    ├── podcast.py        # Dialogue LLM + Gemini multi-speaker TTS
    ├── narration.py      # Script LLM + single-voice TTS
    ├── instagram.py      # Hook LLM + single-voice TTS
    ├── notebooklm.py     # NotebookLM Enterprise API (end-to-end podcast)
    ├── storage.py        # S3 upload → public URL
    ├── webhook.py        # Async HTTP POST callback
    └── html_utils.py     # strip_html() + to_bcp47()
```

---

## How each audio type works

### Podcast (type=`podcast`)

Two-step pipeline — no external podcast library.

**Step 1 — Dialogue generation (LLM)**

The LLM receives the article and a system prompt that enforces a strict line format:

```
Host: Welcome to today's show. We're diving into...
Guest: Really excited about this topic. Let me start with...
Host: Good point. Now, the data shows...
```

Every line must begin with exactly `Host: ` or `Guest: ` (colon + space). No markdown, no stage directions, no blank lines. The `style` option is passed as a hint (e.g. `"educational,conversational"`).

- `LLM_PROVIDER=openai` → GPT-4o-mini, `max_tokens = min(word_count × 2, 4000)`
- `LLM_PROVIDER=google` → Gemini 2.5 Flash with `thinking_budget=0` (disables the reasoning scratchpad that would otherwise pollute the output)

**Step 2 — Audio synthesis (TTS)**

- `TTS_PROVIDER=google` → **Gemini multi-speaker TTS**: the whole transcript is sent in a single API call using `MultiSpeakerVoiceConfig`. Speaker labels `"Host"` and `"Guest"` in the text map to two prebuilt Gemini voices (defaults: `Puck` for Host, `Charon` for Guest). If the transcript exceeds ~3000 characters it is split at turn boundaries into chunks; each chunk is synthesised separately and the resulting PCM blobs are concatenated with pydub before being encoded to MP3.
- `TTS_PROVIDER=openai` → **OpenAI TTS per turn**: each `Host:` / `Guest:` line is sent as a separate OpenAI `tts-1-hd` call with the mapped voice, and the resulting MP3 segments are concatenated with pydub.

Returns `(path_to_mp3, token_usage_dict)`.

---

### Narration (type=`narration`)

Single-speaker audio of the article content.

1. Strip HTML
2. LLM generates a clean spoken script (no markdown, no bullets, `≤ word_count` words)
3. TTS converts the script to MP3

LLM and TTS providers are controlled independently:

- `LLM_PROVIDER=openai` → GPT-4o-mini
- `LLM_PROVIDER=google` → Gemini 2.5 Flash
- `TTS_PROVIDER=openai` → `tts-1-hd` with `voice` option (default `alloy`)
- `TTS_PROVIDER=google` → Gemini TTS with `google_voice` / `google_tts_model` options; PCM 24kHz → MP3 via pydub

Returns `(path_to_mp3, token_usage_dict)`.

---

### NotebookLM podcast (type=`notebooklm_podcast`)

End-to-end podcast generation via [Google NotebookLM Enterprise API](https://cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/podcast-api). Unlike the `podcast` type, there is no separate LLM dialogue step or TTS step — NotebookLM generates both the conversation script and the audio in a single black-box API call.

**Prerequisites**: NotebookLM Enterprise requires allowlist approval from Google, a Google Cloud project with the Discovery Engine API enabled, and a service account with the `roles/discoveryengine.podcastApiUser` IAM role. See [Setup — NotebookLM](#notebooklm-setup) below.

**Pipeline**:
1. Strip HTML via `html_utils.strip_html()` → plain text
2. Map language code to BCP-47 via `html_utils.to_bcp47()`
3. Check the Redis daily usage counter — raise if the daily limit is reached
4. Obtain an OAuth2 access token via Application Default Credentials (ADC)
5. `POST .../projects/{project}/locations/{location}:generatePodcast` with the text content
6. Poll the returned long-running operation every 10 s (up to 10 minutes)
7. Download the completed MP3 via `:download?alt=media`

**Length options**:
- `SHORT` — ~4–5 minutes
- `STANDARD` — ~10 minutes (default)

**Quota**: Google enforces a limit of ~20 podcasts per Google Cloud identity per day. The service tracks usage in Redis (`notebooklm:daily_usage:{YYYY-MM-DD}`) and rejects requests before they hit the API if the limit is reached.

**token_usage** for this type: `{ "notebooklm": { "operation": "<operation-name>" } }`. Google does not expose token counts for this API.

Returns `(path_to_mp3, token_usage_dict)`.

---

### Instagram voiceover (type=`instagram`)

Short punchy hook, ~15–30 s.

1. Strip HTML
2. LLM generates a single ~60-word paragraph (no markdown, conversational, hooks listener immediately)
3. TTS converts it to MP3

Same LLM/TTS provider split as narration. The `voice` option is ignored for Instagram — OpenAI always uses `nova`; Google uses `google_voice` (default `Aoede`).

Returns `(path_to_mp3, token_usage_dict)`.

---

## Setup

### Prerequisites

- Python 3.11+
- ffmpeg (required by pydub for PCM → MP3 encoding; present in the Docker image)
- A Redis instance (see below)

### Redis

The app requires Redis for the job queue.

**Managed Redis** (e.g. Sevalla): set `REDIS_URL` to the connection string — no local Redis needed.

**Local Redis (Docker)**:
```bash
docker run -p 6379:6379 redis:7-alpine
# Then set REDIS_URL=redis://localhost:6379 (this is the default)
```

### Local install

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env — see Env vars section below
uvicorn app.main:app --reload --port 8020
```

### Docker

```bash
docker build -t audiofeed .
docker run -p 8020:8020 --env-file .env audiofeed
```

### NotebookLM setup

Required only for `type="notebooklm_podcast"`.

1. Create or select a Google Cloud project and [enable the Discovery Engine API](https://console.cloud.google.com/apis/library/discoveryengine.googleapis.com).
2. Create a service account and grant it the `roles/discoveryengine.podcastApiUser` IAM role.
3. Download the service account key JSON.
4. Add to `.env`:
   ```
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
   NOTEBOOKLM_PROJECT_ID=your-gcp-project-id
   ```
5. [Request allowlist access](https://cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/podcast-api) from Google (NotebookLM Enterprise requires approval).

---

### Health check

```bash
curl http://localhost:8020/health
# {"status":"healthy","llm_provider":"openai","tts_provider":"google"}
```

Interactive Swagger UI: http://localhost:8020/docs  
Raw OpenAPI spec: http://localhost:8020/openapi.yaml

---

## Env vars

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | yes | `openai` | Which model generates scripts and dialogue. `openai` or `google`. |
| `TTS_PROVIDER` | yes | `openai` | Which engine synthesises audio. `openai` or `google`. |
| `OPENAI_API_KEY` | if either provider is `openai` | — | OpenAI API key (`sk-...`) |
| `GOOGLE_API_KEY` | if either provider is `google` | — | Google / Gemini API key |
| `S3_ENDPOINT_URL` | yes | — | S3-compatible endpoint (e.g. `https://storage.sevalla.com`) |
| `S3_PUBLIC_URL` | no | falls back to endpoint | Public base URL for generated audio links |
| `S3_ACCESS_KEY_ID` | yes | — | S3 access key |
| `S3_SECRET_ACCESS_KEY` | yes | — | S3 secret key |
| `S3_BUCKET_NAME` | yes | `audiofeed-audio` | S3 bucket name |
| `API_SECRET` | yes | — | Shared secret checked against the `X-API-Key` header |
| `REDIS_URL` | no | `redis://localhost:6379` | Redis connection string |
| `PORT` | no | `8020` | Server port (used by `python -m app.main` and Docker) |
| `NOTEBOOKLM_PROJECT_ID` | if using `notebooklm_podcast` | — | GCP project ID that has the Discovery Engine API enabled |
| `NOTEBOOKLM_LOCATION` | no | `global` | GCP location for the NotebookLM API endpoint |
| `NOTEBOOKLM_DAILY_LIMIT` | no | `20` | Max NotebookLM podcasts per day (mirrors Google's quota) |
| `GOOGLE_APPLICATION_CREDENTIALS` | if using `notebooklm_podcast` | — | Path to service account JSON with `roles/discoveryengine.podcastApiUser` |

> **Typical mixed config** (OpenAI for LLM, Gemini for TTS):
> ```
> LLM_PROVIDER=openai
> TTS_PROVIDER=google
> OPENAI_API_KEY=sk-...
> GOOGLE_API_KEY=AIza...
> ```
> Both keys must be set when each provider is used by at least one of `LLM_PROVIDER` / `TTS_PROVIDER`.

---

## API reference

### Authentication

All routes except `GET /health` require:

```
X-API-Key: <API_SECRET>
```

Returns `401` if missing or wrong.

### Error responses

All error responses follow FastAPI's default shape:

```json
{ "detail": "<human-readable message>" }
```

| Status | When |
|---|---|
| `401` | Missing or incorrect `X-API-Key` header |
| `404` | Unknown `job_id` or job expired (after 24 h) |
| `422` | Request body failed validation (missing required field, wrong type, etc.) |

---

### GET /health

```http
GET /health
```

No authentication required.

**Response 200**
```json
{
  "status": "healthy",
  "llm_provider": "openai",
  "tts_provider": "google"
}
```

---

### POST /generate

Queues an audio generation job. Returns immediately.

```http
POST /generate
Content-Type: application/json
X-API-Key: <secret>
```

**Request body**

```jsonc
{
  "type": "podcast",                 // required — "podcast" | "narration" | "instagram" | "notebooklm_podcast"
  "content": "<p>Article...</p>",    // required — HTML or plain text
  "webhook_url": "https://...",      // optional — called on completion or failure
  "options": { ... },                // optional — see below
  "tenant_id": "acme",               // optional — used as S3 key prefix
  "content_type": "article",         // optional — passed through in job/webhook payload
  "content_id": "abc-123"            // optional — passed through in job/webhook payload
}
```

**Response 202**
```json
{ "job_id": "b3d1f2a0-...", "status": "queued" }
```

---

### Options

All fields are optional. Fields irrelevant to the current `type` or provider are silently ignored.

| Field | Type | Default | Applies to | Description |
|---|---|---|---|---|
| `language` | string | `"en"` | all types | ISO 639-1 code (e.g. `"en"`, `"el"`, `"fr"`). Controls LLM output language and TTS voice language. |
| `word_count` | integer 50–2000 | `400` | `podcast`, `narration` | Target dialogue/script length in words. |
| `style` | string | `"engaging,fast-paced"` | `podcast` | Comma-separated style hints for the dialogue LLM (e.g. `"educational,calm"`). |
| `voice` | string | `"alloy"` | `narration` (`TTS_PROVIDER=openai`) | OpenAI TTS voice: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`. |
| `podcast_voice1` | string | `"Puck"` | `podcast` (`TTS_PROVIDER=google`) | Gemini prebuilt voice for the podcast host. |
| `podcast_voice2` | string | `"Charon"` | `podcast` (`TTS_PROVIDER=google`) | Gemini prebuilt voice for the podcast guest. |
| `podcast_openai_voice1` | string | `"alloy"` | `podcast` (`TTS_PROVIDER=openai`) | OpenAI TTS voice for the podcast host: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`. |
| `podcast_openai_voice2` | string | `"echo"` | `podcast` (`TTS_PROVIDER=openai`) | OpenAI TTS voice for the podcast guest: same enum as above. |
| `podcast_instructions` | string | `null` | `podcast` | Free-text instructions for the dialogue LLM (host/guest names, intro/outro, framing, etc.). |
| `google_voice` | string | `"Charon"` (narration) / `"Aoede"` (instagram) | `narration`, `instagram` (`TTS_PROVIDER=google`) | Gemini prebuilt voice name. |
| `google_tts_model` | string | `"gemini-2.5-flash-preview-tts"` | `narration`, `instagram`, `podcast` (`TTS_PROVIDER=google`) | Gemini TTS model ID. |
| `tts_style_prompt` | string | `null` | `narration`, `instagram` | Free-text delivery instruction appended to the LLM prompt (e.g. `"Speak slowly and warmly."`). |
| `notebooklm_length` | `"SHORT"` \| `"STANDARD"` | `"STANDARD"` | `notebooklm_podcast` | Podcast length. `SHORT` ≈ 4–5 min, `STANDARD` ≈ 10 min. |
| `notebooklm_focus` | string | `null` | `notebooklm_podcast` | Optional topic focus hint passed to NotebookLM (e.g. `"Focus on the economic implications"`). |

**Available Gemini prebuilt voices**: `Aoede`, `Charon`, `Fenrir`, `Kore`, `Puck` (and others — check the Gemini TTS docs for the full list).

---

### GET /jobs/{job_id}

Poll job status.

```http
GET /jobs/{job_id}
X-API-Key: <secret>
```

**Response 200**
```jsonc
{
  "job_id": "b3d1f2a0-...",
  "status": "completed",          // "queued" | "processing" | "completed" | "failed"
  "type": "podcast",
  "audio_url": "https://storage.sevalla.com/audiofeed/podcast/podcast_abc123.mp3",
  "duration_seconds": 142.7,      // null until completed
  "error": null,                  // error message string if status="failed"
  "token_usage": {                // null for podcast on OpenAI TTS path
    "llm": { "input_tokens": 512, "output_tokens": 843, "total_tokens": 1355 },
    "tts": { "input_tokens": 843, "output_tokens": null, "total_tokens": null }
  },
  "created_at": "2025-04-12T10:30:00Z",
  "tenant_id": "acme",
  "content_type": "article",
  "content_id": "abc-123"
}
```

**Response 404** — Job not found (expired after 24 h or unknown ID).  
**Response 401** — Missing or wrong `X-API-Key`.

---

### Webhook callback

When `webhook_url` is set, the service fires a `POST` to that URL when the job reaches `completed` or `failed`. The body is the same shape as `GET /jobs/{job_id}`.

The call is best-effort: failures are logged and do not affect the job result. Timeout is 30 s.

---

## Examples

### Podcast (OpenAI LLM + Gemini TTS)

```bash
curl -X POST http://localhost:8020/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret" \
  -d '{
    "type": "podcast",
    "content": "<h1>The Future of AI</h1><p>Long article body...</p>",
    "webhook_url": "https://webhook.site/your-id",
    "options": {
      "language": "en",
      "word_count": 600,
      "style": "educational,conversational",
      "podcast_voice1": "Puck",
      "podcast_voice2": "Charon"
    }
  }'
```

### Narration (OpenAI end-to-end)

```bash
curl -X POST http://localhost:8020/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret" \
  -d '{
    "type": "narration",
    "content": "<p>Article body here...</p>",
    "options": {
      "language": "en",
      "voice": "nova",
      "word_count": 300
    }
  }'
```

### Narration (Google end-to-end)

```bash
curl -X POST http://localhost:8020/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret" \
  -d '{
    "type": "narration",
    "content": "<p>Article body here...</p>",
    "options": {
      "language": "el",
      "google_voice": "Fenrir",
      "tts_style_prompt": "Speak slowly and clearly."
    }
  }'
```

### Instagram voiceover

```bash
curl -X POST http://localhost:8020/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret" \
  -d '{
    "type": "instagram",
    "content": "<p>Your article...</p>",
    "options": {
      "language": "el",
      "google_voice": "Aoede",
      "tts_style_prompt": "Energetic and upbeat."
    }
  }'
```

### NotebookLM podcast

```bash
curl -X POST http://localhost:8020/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret" \
  -d '{
    "type": "notebooklm_podcast",
    "content": "<h1>The Future of AI</h1><p>Long article body...</p>",
    "webhook_url": "https://webhook.site/your-id",
    "tenant_id": "acme",
    "options": {
      "language": "en",
      "notebooklm_length": "STANDARD",
      "notebooklm_focus": "Focus on practical implications for businesses"
    }
  }'
```

> NotebookLM jobs take significantly longer than other types (the operation can run for several minutes). Use `webhook_url` instead of polling to avoid holding open connections.

### Poll until done

```bash
curl http://localhost:8020/jobs/b3d1f2a0-... \
  -H "X-API-Key: your-secret"
```

---

## Job lifecycle

```
queued → processing → completed
                    → failed
```

- Jobs expire from Redis after **24 hours**.
- The worker makes **one attempt** (no auto-retry). On failure, `status=failed` and `error` contains the exception message.
- The worker runs inside the FastAPI process. No separate worker process is needed.

---

## S3 key layout

```
audiofeed/
  {tenant_id}/podcast/{filename}.mp3     # when tenant_id is set
  podcast/{filename}.mp3                  # when tenant_id is omitted
  {tenant_id}/narration/{filename}.mp3
  narration/{filename}.mp3
  {tenant_id}/instagram/{filename}.mp3
  instagram/{filename}.mp3
  {tenant_id}/notebooklm_podcast/{filename}.mp3
  notebooklm_podcast/{filename}.mp3
```

`S3_PUBLIC_URL` is used as the base for the returned `audio_url`. Falls back to `S3_ENDPOINT_URL` if `S3_PUBLIC_URL` is not set.
