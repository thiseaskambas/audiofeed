"""Redis-backed job store: create, get, update."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import arq

JOB_TTL = 86_400  # 24h in seconds
_KEY = "job:{}"

_redis: arq.ArqRedis | None = None


def init_redis(pool: arq.ArqRedis) -> None:
    global _redis
    _redis = pool


def get_redis() -> arq.ArqRedis:
    if _redis is None:
        raise RuntimeError("Redis pool not initialised")
    return _redis


async def create_job(
    job_type: str,
    *,
    webhook_url: str | None = None,
    options: dict[str, Any] | None = None,
    content: str | None = None,
) -> str:
    job_id = str(uuid.uuid4())
    payload = {
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
    await get_redis().set(_KEY.format(job_id), json.dumps(payload), ex=JOB_TTL)
    return job_id


async def get_job(job_id: str) -> dict[str, Any] | None:
    raw = await get_redis().get(_KEY.format(job_id))
    return json.loads(raw) if raw else None


async def update_job(
    job_id: str,
    *,
    status: str | None = None,
    audio_url: str | None = None,
    duration_seconds: int | float | None = None,
    error: str | None = None,
) -> None:
    job = await get_job(job_id)
    if job is None:
        return
    if status is not None:
        job["status"] = status
    if audio_url is not None:
        job["audio_url"] = audio_url
    if duration_seconds is not None:
        job["duration_seconds"] = duration_seconds
    if error is not None:
        job["error"] = error
    await get_redis().set(_KEY.format(job_id), json.dumps(job), ex=JOB_TTL)
