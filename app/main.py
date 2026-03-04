"""FastAPI app: lifespan startup validation + provider config, health."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routes import generate


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_for_startup()

    # Ensure podcastfy output dirs exist (relative to CWD, which is /app in Docker)
    os.makedirs("data/audio/tmp", exist_ok=True)
    os.makedirs("data/transcripts", exist_ok=True)

    # Configure Google generative AI once at startup (not per-request)
    if settings.provider == "google" and settings.google_api_key:
        import google.generativeai as genai
        genai.configure(api_key=settings.google_api_key)
        os.environ["GEMINI_API_KEY"] = settings.google_api_key

    yield


app = FastAPI(
    title="Audiofeed",
    description="Article → audio generation (podcast, narration, Instagram voiceover)",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(generate.router, prefix="", tags=["generate"])
