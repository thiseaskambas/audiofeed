"""ARQ worker: processes audio generation jobs from the Redis queue."""
from __future__ import annotations
import logging, os
from pathlib import Path
import arq
from arq.connections import RedisSettings
from app.config import get_settings
from app.jobs import init_redis, get_job, update_job
from app.services import podcast, narration, instagram, notebooklm
from app.services.storage import upload_audio
from app.services.webhook import fire_webhook

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    # When running in-process (started from main.py lifespan), jobs.py is already
    # initialised with the API's Redis pool. When running as a standalone worker
    # (arq app.worker.WorkerSettings), initialise it from ARQ's injected pool.
    from app.jobs import get_redis as _get_redis
    try:
        _get_redis()
    except RuntimeError:
        init_redis(ctx["redis"])


async def run_job(ctx: dict, job_id: str) -> None:
    job = await get_job(job_id)
    if not job or job["status"] != "queued":
        return  # already processed or not found

    await update_job(job_id, status="processing")
    opts = job.get("options") or {}
    content = job.get("content")

    if not content:
        await update_job(job_id, status="failed", error="Missing content")
        await _maybe_webhook(job)
        return

    try:
        token_usage = None
        if job["type"] == "podcast":
            path, token_usage = await podcast.generate_podcast_audio(
                content,
                language=opts.get("language", "en"),
                word_count=opts.get("word_count", 400),
                style=opts.get("style", "engaging,fast-paced"),
                voice1=opts.get("podcast_voice1", "Puck"),
                voice2=opts.get("podcast_voice2", "Charon"),
                openai_voice1=opts.get("podcast_openai_voice1", "alloy"),
                openai_voice2=opts.get("podcast_openai_voice2", "echo"),
                google_tts_model=opts.get("google_tts_model", "gemini-2.5-flash-preview-tts"),
                instructions=opts.get("podcast_instructions"),
            )
            prefix = "podcast"
        elif job["type"] == "narration":
            path, token_usage = await narration.generate_narration_audio(
                content, language=opts.get("language", "en"),
                voice=opts.get("voice", "alloy"), word_count=opts.get("word_count", 400),
                google_voice=opts.get("google_voice", "Charon"),
                google_tts_model=opts.get("google_tts_model", "gemini-2.5-flash-preview-tts"),
                tts_style_prompt=opts.get("tts_style_prompt"),
            )
            prefix = "narration"
        elif job["type"] == "instagram":
            path, token_usage = await instagram.generate_instagram_audio(
                content, language=opts.get("language", "en"),
                google_voice=opts.get("google_voice", "Aoede"),
                google_tts_model=opts.get("google_tts_model", "gemini-2.5-flash-preview-tts"),
                tts_style_prompt=opts.get("tts_style_prompt"),
            )
            prefix = "instagram"
        elif job["type"] == "notebooklm_podcast":
            path, token_usage = await notebooklm.generate_notebooklm_podcast(
                content,
                language=opts.get("language", "en"),
                length=opts.get("notebooklm_length", "STANDARD"),
                focus=opts.get("notebooklm_focus"),
                job_id=job_id,
            )
            prefix = "notebooklm_podcast"
        else:
            await update_job(job_id, status="failed", error=f"Unknown type: {job['type']}")
            await _maybe_webhook(job)
            return

        tenant_id = job.get("tenant_id")
        key_prefix = f"{tenant_id}/{prefix}" if tenant_id else prefix
        audio_url = upload_audio(path, key_prefix=key_prefix)
        duration = _duration(path)
        await update_job(job_id, status="completed", audio_url=audio_url, duration_seconds=duration, token_usage=token_usage)
        Path(path).unlink(missing_ok=True)
        await _maybe_webhook(job)

    except Exception as e:
        logger.exception("Job %s failed", job_id)
        await update_job(job_id, status="failed", error=str(e))
        await _maybe_webhook(job)


def _duration(path: str) -> float | None:
    try:
        from mutagen.mp3 import MP3
        return float(MP3(path).info.length)
    except Exception:
        return None


async def _maybe_webhook(job: dict) -> None:
    if job.get("webhook_url"):
        final = await get_job(job["job_id"])
        if final:
            await fire_webhook(job["webhook_url"], {
                k: final.get(k) for k in
                ("job_id", "status", "type", "audio_url", "duration_seconds", "error", "token_usage",
                 "created_at", "tenant_id", "content_type", "content_id")
            })


class WorkerSettings:
    functions = [run_job]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = 600   # 10 min max before ARQ considers the job hung
    keep_result = 0     # job state lives in job:{id} keys, not ARQ result keys
    max_tries = 1       # no auto-retry (crash recovery is out of scope for now)
