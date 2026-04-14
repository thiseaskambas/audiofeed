# Audio Job Reconciliation

Audiofeed uses a webhook-first design: when a job completes or fails, it POSTs the result to the `webhook_url` supplied at job creation. If that delivery fails (network error, caller temporarily unreachable), the caller's local record may stay stuck at `queued` indefinitely.

`GET /jobs/{job_id}` exists for exactly this purpose — it lets callers recover stale records by polling.

## Normal flow

```
POST /generate  →  202 Accepted (job_id)
                     ↓
              [job runs asynchronously]
                     ↓
         POST {webhook_url}  →  completed / failed
```

## When to poll

Poll when a locally-tracked job has been in `queued` state longer than your expected processing time. A conservative threshold is **15 minutes** — well within the 24-hour Redis TTL and safely above the maximum job timeout (10 minutes).

## Endpoint reference

```
GET /jobs/{job_id}
Authorization: X-API-Key: <secret>
```

**Response**

```json
{
  "job_id": "06f2abf0-948e-4384-a17d-402483bbf0b4",
  "status": "completed",
  "type": "narration",
  "audio_url": "https://...",
  "duration_seconds": 142.5,
  "error": null,
  "token_usage": { ... },
  "created_at": "2026-04-10T14:30:45Z",
  "tenant_id": null,
  "content_type": null,
  "content_id": null
}
```

Status values: `queued` | `processing` | `completed` | `failed`

See [token-usage.md](./token-usage.md) for the `token_usage` field shape.

## Handling each status

| Status | Recommended action |
|---|---|
| `queued` | Still waiting to run. Check again later. |
| `processing` | Job is running. Check again later. |
| `completed` | Update local record with `audio_url`, `duration_seconds`, `token_usage`. |
| `failed` | Update local record with `error`. |
| HTTP 404 | Job TTL expired (24h). Mark local record as permanently failed. |

## Redis TTL

Job records are retained for **24 hours** after creation. Reconciliation should run within this window. If a job is older than 24 hours and still `queued` locally, treat it as failed.
