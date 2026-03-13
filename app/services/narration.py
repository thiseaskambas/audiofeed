"""Narration: LLM script (≤400 words) + TTS single speaker → MP3."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from app.config import get_settings
from app.services.html_utils import strip_html, to_bcp47

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP_DIR = os.path.join(_BASE_DIR, "data", "audio", "tmp")

NARRATION_SYSTEM = """You are a professional narrator. Given an article, produce a clean spoken script suitable for a single narrator.
- Use clear, conversational language. No markdown, no bullet points, no headers.
- Keep within the requested maximum word count.
- Write in the same language as the article unless instructed otherwise."""


def _script_openai(content: str, language: str, max_words: int) -> str:
    from openai import OpenAI
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    lang_instruction = "Keep the script in English." if language == "en" else f"Keep the script in {language}."
    word_limit_instruction = f"Limit the script to {max_words} words maximum."
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"{NARRATION_SYSTEM} {lang_instruction} {word_limit_instruction}",
            },
            {"role": "user", "content": f"Article:\n\n{content[:15000]}"},
        ],
        max_tokens=600,
    )
    return (resp.choices[0].message.content or "").strip()


def _script_google(content: str, language: str, max_words: int, style_prompt: str | None = None) -> str:
    from google import genai
    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)
    lang_instruction = "Keep the script in English." if language == "en" else f"Keep the script in {language}."
    style_instruction = f"\nDelivery style: {style_prompt}" if style_prompt else ""
    prompt = f"""{NARRATION_SYSTEM} {lang_instruction}{style_instruction}

Article:

{content[:15000]}

Produce the narration script (max {max_words} words):"""
    r = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return (r.text or "").strip()


def _tts_openai(script: str, voice: str, out_path: str) -> None:
    from openai import OpenAI
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    with client.audio.speech.with_streaming_response.create(
        model="tts-1-hd",   
        voice=voice or "alloy",
        input=script[:4096],
    ) as response:
        response.stream_to_file(out_path)


def _tts_gemini(
    script: str,
    out_path: str,
    language: str,
    voice_name: str,
    tts_model: str,
) -> None:
    from google import genai
    from google.genai import types
    from pydub import AudioSegment

    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)
    lang_code = to_bcp47(language)

    response = client.models.generate_content(
        model=tts_model,
        contents=script[:4000],
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                language_code=lang_code,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                ),
            ),
        ),
    )
    audio_bytes = response.candidates[0].content.parts[0].inline_data.data
    # Gemini TTS returns PCM 24kHz 16-bit mono → encode to MP3 via pydub/ffmpeg
    AudioSegment(
        data=audio_bytes, sample_width=2, frame_rate=24000, channels=1
    ).export(out_path, format="mp3")


async def generate_narration_audio(
    content: str,
    *,
    language: str = "en",
    voice: str = "alloy",
    word_count: int = 400,
    google_voice: str = "Charon",
    google_tts_model: str = "gemini-2.5-flash-preview-tts",
    tts_style_prompt: str | None = None,
) -> str:
    """Strip HTML → LLM script → TTS → write to temp file. Returns path to MP3."""
    settings = get_settings()
    plain = strip_html(content)
    if not plain.strip():
        raise ValueError("Content is empty after stripping HTML")

    os.makedirs(_TMP_DIR, exist_ok=True)
    out_path = os.path.join(_TMP_DIR, f"narration_{uuid.uuid4().hex}.mp3")

    if settings.provider == "openai":
        script = _script_openai(plain, language, word_count)
        _tts_openai(script, voice, out_path)
    else:
        script = _script_google(plain, language, word_count, tts_style_prompt)
        _tts_gemini(script, out_path, language, google_voice, google_tts_model)

    return out_path
