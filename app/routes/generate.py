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

GenerateType = Literal["podcast", "narration", "instagram", "notebooklm_podcast"]


class GenerateOptions(BaseModel):
    language: str = "en"
    voice: str = "alloy"
    word_count: int = Field(default=600, ge=50, le=4000)
    style: str = "engaging,fast-paced"
    # Gemini TTS controls (google tts_provider only)
    google_voice: str | None = None
    google_tts_model: str = "gemini-2.5-flash-preview-tts"
    tts_style_prompt: str | None = None
    # Podcast multi-speaker voices — Gemini (tts_provider=google)
    podcast_voice1: str = "Puck"           # Host voice
    podcast_voice2: str = "Charon"         # Guest voice
    # Podcast multi-speaker voices — OpenAI (tts_provider=openai)
    podcast_openai_voice1: str = "alloy"   # Host voice
    podcast_openai_voice2: str = "echo"    # Guest voice
    # Podcast LLM script customisation
    podcast_instructions: str | None = None  # Free-text instructions for the dialogue writer
    # NotebookLM podcast options (type="notebooklm_podcast" only)
    notebooklm_length: Literal["SHORT", "STANDARD"] = "STANDARD"
    notebooklm_focus: str | None = None    # Optional topic focus hint for NotebookLM


class GenerateRequest(BaseModel):
    type: GenerateType
    content: str = Field(..., min_length=1)
    webhook_url: str | None = None
    options: GenerateOptions | None = None
    tenant_id: str | None = None
    content_type: str | None = None
    content_id: str | None = None


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
    token_usage: dict | None
    created_at: str
    tenant_id: str | None
    content_type: str | None
    content_id: str | None


# --- Auth ---

def require_api_key(x_api_key: str | None = Header(None)) -> str:
    secret = get_settings().api_secret
    if not secret or x_api_key != secret:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return x_api_key


# --- Routes ---

@router.get("/health")
def health() -> dict[str, str]:
    s = get_settings()
    return {"status": "healthy", "llm_provider": s.llm_provider, "tts_provider": s.tts_provider}


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
        tenant_id=body.tenant_id,
        content_type=body.content_type,
        content_id=body.content_id,
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
        token_usage=job.get("token_usage"),
        created_at=job["created_at"],
        tenant_id=job.get("tenant_id"),
        content_type=job.get("content_type"),
        content_id=job.get("content_id"),
    )
