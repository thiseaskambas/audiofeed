"""In-memory job store: create, get, update. Upgradeable to Redis later."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

# job_id -> job dict
_store: dict[str, dict[str, Any]] = {}

_JOB_TTL = timedelta(hours=24)


def _cleanup() -> None:
    """Remove jobs older than 24h. Called on every create_job to prevent unbounded growth."""
    cutoff = datetime.now(tz=timezone.utc) - _JOB_TTL
    stale = [
        jid for jid, j in list(_store.items())
        if datetime.fromisoformat(j["created_at"].replace("Z", "+00:00")) < cutoff
    ]
    for jid in stale:
        del _store[jid]


def create_job(
    job_type: str,
    *,
    webhook_url: str | None = None,
    options: dict[str, Any] | None = None,
    content: str | None = None,
) -> str:
    _cleanup()
    job_id = str(uuid.uuid4())
    _store[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "type": job_type,
        "audio_url": None,
        "duration_seconds": None,
        "error": None,
        "created_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "webhook_url": webhook_url,
        "options": options or {},
        "content": content,
    }
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    return _store.get(job_id)


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    audio_url: str | None = None,
    duration_seconds: int | float | None = None,
    error: str | None = None,
) -> None:
    if job_id not in _store:
        return
    job = _store[job_id]
    if status is not None:
        job["status"] = status
    if audio_url is not None:
        job["audio_url"] = audio_url
    if duration_seconds is not None:
        job["duration_seconds"] = duration_seconds
    if error is not None:
        job["error"] = error
