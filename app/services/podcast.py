"""Podcastfy integration: two-speaker dialogue, 2–5 min. Run sync in executor."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from app.config import get_settings
from app.services.html_utils import strip_html

logger = logging.getLogger(__name__)

# Absolute path to project root so podcastfy writes to the right dirs regardless of CWD
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP_DIR = os.path.join(_BASE_DIR, "data", "audio", "tmp")


def _generate_podcast_sync(
    text: str,
    tts_model: str,
    conversation_config: dict[str, Any],
    longform: bool = False,
) -> str:
    """Synchronous call to podcastfy (blocks; run via run_in_executor)."""
    from podcastfy.client import generate_podcast
    return generate_podcast(
        text=text,
        tts_model=tts_model,
        conversation_config=conversation_config,
        longform=longform,
    )


async def generate_podcast_audio(
    content: str,
    *,
    language: str = "en",
    word_count: int = 400,
    style: str = "engaging,fast-paced",
) -> str:
    """
    Strip HTML, run podcastfy in executor (sync), return path to generated MP3.
    tts_model is "openai" or "gemini" from config provider.
    GEMINI_API_KEY and genai.configure() are set once at app startup (main.py lifespan).
    """
    settings = get_settings()
    tts_model = "openai" if settings.provider == "openai" else "gemini"

    plain = strip_html(content)
    if not plain.strip():
        raise ValueError("Content is empty after stripping HTML")

    lang_label = "English" if language == "en" else language
    conversation_config = {
        "word_count": word_count,
        "conversation_style": style,
        "output_language": lang_label,
        "text_to_speech": {
            "output_directories": {
                "transcripts": os.path.join(_BASE_DIR, "data", "transcripts"),
                "audio": os.path.join(_BASE_DIR, "data", "audio"),
            },
            "temp_audio_dir": _TMP_DIR + os.sep,
        },
    }

    loop = asyncio.get_running_loop()
    audio_path = await loop.run_in_executor(
        None,
        lambda: _generate_podcast_sync(
            plain,
            tts_model=tts_model,
            conversation_config=conversation_config,
            longform=False,
        ),
    )
    return audio_path
