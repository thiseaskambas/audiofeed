"""Instagram: LLM 60-word hook + TTS (upbeat voice, 15–30s)."""

from __future__ import annotations

import os
import uuid

from app.config import get_settings
from app.services.html_utils import strip_html

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP_DIR = os.path.join(_BASE_DIR, "data", "audio", "tmp")

INSTAGRAM_SYSTEM = """You are a social media copywriter. Given an article, write a single punchy hook for an Instagram voiceover.
- Exactly around 60 words. One short paragraph.
- Engaging, conversational, hook the listener in 15–30 seconds.
- No markdown. Plain text only."""


def _script_openai(content: str, language: str) -> str:
    from openai import OpenAI
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    lang_instruction = "Write in English." if language == "en" else f"Write in {language}."
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": INSTAGRAM_SYSTEM + " " + lang_instruction},
            {"role": "user", "content": f"Article:\n\n{content[:8000]}"},
        ],
        max_tokens=150,
    )
    return (resp.choices[0].message.content or "").strip()


def _script_google(content: str, language: str, style_prompt: str | None = None) -> str:
    from google import genai
    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)
    lang_instruction = "Write in English." if language == "en" else f"Write in {language}."
    style_instruction = f"\nDelivery style: {style_prompt}" if style_prompt else ""
    prompt = f"""{INSTAGRAM_SYSTEM} {lang_instruction}{style_instruction}

Article:

{content[:8000]}

Punchy 60-word hook:"""
    r = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return (r.text or "").strip()


def _tts_openai(script: str, out_path: str) -> None:
    from openai import OpenAI
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    with client.audio.speech.with_streaming_response.create(
        model="tts-1-hd",
        voice="nova",
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

    response = client.models.generate_content(
        model=tts_model,
        contents=script[:4000],
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
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


async def generate_instagram_audio(
    content: str,
    *,
    language: str = "en",
    google_voice: str = "Aoede",
    google_tts_model: str = "gemini-2.5-flash-preview-tts",
    tts_style_prompt: str | None = None,
) -> str:
    """Strip HTML → LLM 60-word hook → TTS (upbeat) → write to temp file. Returns path to MP3."""
    settings = get_settings()
    plain = strip_html(content)
    if not plain.strip():
        raise ValueError("Content is empty after stripping HTML")

    os.makedirs(_TMP_DIR, exist_ok=True)
    out_path = os.path.join(_TMP_DIR, f"instagram_{uuid.uuid4().hex}.mp3")

    if settings.provider == "openai":
        script = _script_openai(plain, language)
        _tts_openai(script, out_path)
    else:
        script = _script_google(plain, language, tts_style_prompt)
        _tts_gemini(script, out_path, language, google_voice, google_tts_model)

    return out_path
