# Audiofeed

Python REST API microservice that turns article content (markdown or HTML) into audio: **podcast** (dialogue), **narration**, or **Instagram** voiceover. Uses async jobs with webhook callbacks; uploads to Sevalla S3.

## Stack

- **Framework:** FastAPI
- **Podcast (dialogue):** [podcastfy](https://github.com/souzatharsis/podcastfy) (run in executor)
- **Narration / Instagram:** LLM (gpt-4o-mini or gemini-1.5-flash) + TTS (OpenAI or Google Cloud)
- **Storage:** boto3 → Sevalla S3
- **Auth:** `X-API-Key` header (shared secret)

## Project structure

```
app/
├── main.py           # FastAPI app, startup validation
├── config.py         # Env settings + validate()
├── jobs.py           # In-memory job store
├── routes/
│   └── generate.py   # POST /generate, GET /jobs/{id}, GET /health
└── services/
    ├── html_utils.py # Strip HTML (BeautifulSoup)
    ├── podcast.py    # podcastfy wrapper (dialogue)
    ├── narration.py  # LLM script + TTS (single speaker)
    ├── instagram.py  # LLM 60-word hook + TTS (nova / upbeat)
    ├── storage.py    # S3 upload → public URL
    └── webhook.py    # httpx POST callback
```

## Setup

1. Copy env template and set values:
   ```bash
   cp .env.example .env
   # Edit .env: PROVIDER, API keys, S3, API_SECRET
   ```
2. Install and run:
   ```bash
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
3. Health:
   ```bash
   curl http://localhost:8000/health
   ```
4. Queue a job (use [webhook.site](https://webhook.site) for callback):
   ```bash
   curl -X POST http://localhost:8000/generate \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your-secret" \
     -d '{"type":"narration","content":"<p>Your article here.</p>","webhook_url":"https://webhook.site/your-id"}'
   ```
5. Poll status:
   ```bash
   curl http://localhost:8000/jobs/{job_id} -H "X-API-Key: your-secret"
   ```
6. Docker:
   ```bash
   docker build -t audiofeed .
   docker run -p 8000:8000 --env-file .env audiofeed
   ```
   For Google TTS, mount credentials:  
   `-v /path/to/creds.json:/app/google-credentials.json`

## API

- **GET /health** — `{ "status": "healthy", "provider": "openai" }` (no auth)
- **POST /generate** — 202, body: `{ "job_id", "status": "queued" }` (requires `X-API-Key`)
- **GET /jobs/{job_id}** — Job status and `audio_url` when completed (requires `X-API-Key`)

Webhook payload (POST to `webhook_url` when done): same shape as GET /jobs/{id}.

See [openapi.yaml](openapi.yaml) for the full contract.

## Env vars

| Variable | Description |
|----------|-------------|
| `PROVIDER` | `openai` or `google` |
| `OPENAI_API_KEY` | Required if `PROVIDER=openai` |
| `GOOGLE_API_KEY` | Required if `PROVIDER=google` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Google TTS JSON key file |
| `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME` | Sevalla S3 |
| `API_SECRET` | Shared secret for `X-API-Key` header |
