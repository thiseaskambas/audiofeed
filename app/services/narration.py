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
- Maximum 400 words.
- Write in the same language as the article unless instructed otherwise."""


def _script_openai(content: str, language: str, max_words: int) -> str:
    from openai import OpenAI
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    lang_instruction = "Keep the script in English." if language == "en" else f"Keep the script in {language}."
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": NARRATION_SYSTEM + " " + lang_instruction},
            {"role": "user", "content": f"Article:\n\n{content[:15000]}"},
        ],
        max_tokens=600,
    )
    return (resp.choices[0].message.content or "").strip()


def _script_google(content: str, language: str, max_words: int) -> str:
    # genai.configure() is called once at startup (app/main.py lifespan)
    import google.generativeai as genai
    model = genai.GenerativeModel("gemini-1.5-flash")
    lang_instruction = "Keep the script in English." if language == "en" else f"Keep the script in {language}."
    prompt = f"""{NARRATION_SYSTEM} {lang_instruction}

Article:

{content[:15000]}

Produce the narration script (max {max_words} words):"""
    r = model.generate_content(prompt)
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


def _tts_google(script: str, out_path: str, language: str) -> None:
    from google.cloud import texttospeech
    client = texttospeech.TextToSpeechClient()
    lang_code = to_bcp47(language)
    synthesis_input = texttospeech.SynthesisInput(text=script[:5000])
    voice_cfg = texttospeech.VoiceSelectionParams(
        language_code=lang_code,
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
    )
    audio_cfg = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
    )
    resp = client.synthesize_speech(
        input=synthesis_input,
        voice=voice_cfg,
        audio_config=audio_cfg,
    )
    Path(out_path).write_bytes(resp.audio_content)


async def generate_narration_audio(
    content: str,
    *,
    language: str = "en",
    voice: str = "alloy",
    word_count: int = 400,
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
        script = _script_google(plain, language, word_count)
        _tts_google(script, out_path, language)

    return out_path
