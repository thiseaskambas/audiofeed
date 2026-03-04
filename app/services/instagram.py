"""Instagram: LLM 60-word hook + TTS (upbeat voice, 15–30s)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.config import get_settings
from app.services.html_utils import strip_html, to_bcp47

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


def _script_google(content: str, language: str) -> str:
    # genai.configure() is called once at startup (app/main.py lifespan)
    import google.generativeai as genai
    model = genai.GenerativeModel("gemini-1.5-flash")
    lang_instruction = "Write in English." if language == "en" else f"Write in {language}."
    prompt = f"""{INSTAGRAM_SYSTEM} {lang_instruction}

Article:

{content[:8000]}

Punchy 60-word hook:"""
    r = model.generate_content(prompt)
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


def _tts_google(script: str, out_path: str, language: str) -> None:
    from google.cloud import texttospeech
    client = texttospeech.TextToSpeechClient()
    lang_code = to_bcp47(language)
    synthesis_input = texttospeech.SynthesisInput(text=script[:5000])
    voice_cfg = texttospeech.VoiceSelectionParams(
        language_code=lang_code,
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
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


async def generate_instagram_audio(
    content: str,
    *,
    language: str = "en",
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
        script = _script_google(plain, language)
        _tts_google(script, out_path, language)

    return out_path
