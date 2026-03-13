"""POST /generate, GET /jobs/{id}, GET /health. API key auth + background worker."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field

from app.config import get_settings
from app.jobs import create_job, get_job, get_redis

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
    google_voice: str | None = None
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


# --- Routes ---

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "provider": get_settings().provider}


@router.post("/generate", response_model=GenerateResponse, status_code=202)
async def generate(
    body: GenerateRequest,
    _: str = Depends(require_api_key),
) -> GenerateResponse:
    opts = (
        body.options.model_dump(exclude_unset=True, exclude_none=True)
        if body.options
        else {}
    )
    job_id = await create_job(
        body.type,
        webhook_url=body.webhook_url,
        options=opts,
        content=body.content,
    )
    await get_redis().enqueue_job("run_job", job_id)
    return GenerateResponse(job_id=job_id, status="queued")


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(
    job_id: str,
    _: str = Depends(require_api_key),
) -> JobResponse:
    job = await get_job(job_id)
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
