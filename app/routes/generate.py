"""POST /generate, GET /jobs/{id}, GET /health. API key auth + background worker."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header
from pydantic import BaseModel, Field

from app.config import get_settings
from app.jobs import create_job, get_job, update_job
from app.services import podcast, narration, instagram
from app.services.storage import upload_audio
from app.services.webhook import fire_webhook

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Schemas ---

GenerateType = Literal["podcast", "narration", "instagram"]


class GenerateOptions(BaseModel):
    language: str = "en"
    voice: str = "alloy"
    word_count: int = Field(default=400, ge=50, le=2000)
    style: str = "engaging,fast-paced"
    # Gemini TTS controls (google provider only)
    google_voice: str = "Charon"
    google_tts_model: str = "gemini-2.5-flash-preview-tts"
    tts_style_prompt: str | None = None


class GenerateRequest(BaseModel):
    type: GenerateType
    content: str = Field(..., min_length=1)
    webhook_url: str | None = None
    options: GenerateOptions | None = None


class GenerateResponse(BaseModel):
    job_id: str
    status: Literal["queued"] = "queued"


class JobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    type: str
    audio_url: str | None
    duration_seconds: float | None
    error: str | None
    created_at: str


# --- Auth ---

def require_api_key(x_api_key: str | None = Header(None)) -> str:
    secret = get_settings().api_secret
    if not secret or x_api_key != secret:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return x_api_key


# --- Helpers ---

def _duration_seconds(path: str) -> float | None:
    try:
        from mutagen.mp3 import MP3
        audio = MP3(path)
        return float(audio.info.length)
    except Exception:
        return None


def _job_payload(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "type": job["type"],
        "audio_url": job.get("audio_url"),
        "duration_seconds": job.get("duration_seconds"),
        "error": job.get("error"),
        "created_at": job["created_at"],
    }


async def _run_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job or job["status"] != "queued":
        return
    update_job(job_id, status="processing")
    opts = job.get("options") or {}
    content = job.get("content")
    if not content:
        update_job(job_id, status="failed", error="Missing content")
        if job.get("webhook_url"):
            await fire_webhook(job["webhook_url"], _job_payload(get_job(job_id) or {}))
        return
    try:
        if job["type"] == "podcast":
            path = await podcast.generate_podcast_audio(
                content,
                language=opts.get("language", "en"),
                word_count=opts.get("word_count", 400),
                style=opts.get("style", "engaging,fast-paced"),
            )
            prefix = "podcast"
        elif job["type"] == "narration":
            path = await narration.generate_narration_audio(
                content,
                language=opts.get("language", "en"),
                voice=opts.get("voice", "alloy"),
                word_count=opts.get("word_count", 400),
                google_voice=opts.get("google_voice", "Charon"),
                google_tts_model=opts.get("google_tts_model", "gemini-2.5-flash-preview-tts"),
                tts_style_prompt=opts.get("tts_style_prompt"),
            )
            prefix = "narration"
        elif job["type"] == "instagram":
            path = await instagram.generate_instagram_audio(
                content,
                language=opts.get("language", "en"),
                google_voice=opts.get("google_voice", "Aoede"),
                google_tts_model=opts.get("google_tts_model", "gemini-2.5-flash-preview-tts"),
                tts_style_prompt=opts.get("tts_style_prompt"),
            )
            prefix = "instagram"
        else:
            update_job(job_id, status="failed", error=f"Unknown type: {job['type']}")
            if job.get("webhook_url"):
                await fire_webhook(job["webhook_url"], _job_payload(get_job(job_id) or {}))
            return
        audio_url = upload_audio(path, key_prefix=prefix)
        duration = _duration_seconds(path)
        update_job(job_id, status="completed", audio_url=audio_url, duration_seconds=duration)
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
        if job.get("webhook_url"):
            await fire_webhook(job["webhook_url"], _job_payload(get_job(job_id) or {}))
    except Exception as e:
        logger.exception("Job %s failed", job_id)
        update_job(job_id, status="failed", error=str(e))
        if job.get("webhook_url"):
            await fire_webhook(job["webhook_url"], _job_payload(get_job(job_id) or {}))


# --- Routes ---

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "provider": get_settings().provider}


@router.post("/generate", response_model=GenerateResponse, status_code=202)
def generate(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_api_key),
) -> GenerateResponse:
    opts = (body.options or GenerateOptions()).model_dump()
    job_id = create_job(
        body.type,
        webhook_url=body.webhook_url,
        options=opts,
        content=body.content,
    )
    background_tasks.add_task(_run_job, job_id)
    return GenerateResponse(job_id=job_id, status="queued")


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job_status(
    job_id: str,
    _: str = Depends(require_api_key),
) -> JobResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        type=job["type"],
        audio_url=job.get("audio_url"),
        duration_seconds=job.get("duration_seconds"),
        error=job.get("error"),
        created_at=job["created_at"],
    )
