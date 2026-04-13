"""Podcast: LLM dialogue (Host/Guest) + Gemini multi-speaker TTS → MP3."""

from __future__ import annotations

import logging
import os
import uuid

from app.config import get_settings
from app.services.html_utils import strip_html, to_bcp47

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP_DIR = os.path.join(_BASE_DIR, "data", "audio", "tmp")

DIALOG_SYSTEM = """You are a podcast scriptwriter. Given an article, write a natural two-person podcast dialogue.

Speaker roles:
- Host: a curious, enthusiastic interviewer. Asks questions, reacts with surprise or delight, keeps the conversation moving.
- Guest: a knowledgeable, articulate explainer. Digs into detail, gives examples, occasionally qualifies or corrects themselves.

Naturalness rules — these are mandatory, not optional:
- Include disfluencies: um, uh, you know, I mean, like, kind of, sort of, actually, basically.
- Include back-channel responses on their own turn: "Right.", "Exactly.", "Yeah, totally.", "Mm-hmm.", "That makes sense.", "Fascinating.", "No kidding."
- Include false starts and self-corrections: "It's basically—well, it's more nuanced than that."
- Include genuine reactions: "Wait, really?", "Oh, that's interesting.", "Huh, I hadn't thought of that.", "Wow.", "That's wild."
- Vary turn lengths naturally: short punchy reactions (1-2 sentences) mixed with longer explanations (4-6 sentences).
- Use contractions throughout: it's, that's, we're, isn't, can't, don't, I've, you'd.

Structure:
1. Warm, natural intro where Host sets up the topic casually (not formally).
2. Main discussion broken into 3-5 natural topic segments with back-and-forth.
3. Brief, conversational conclusion — no formal sign-offs.

Format rules (strict — the audio pipeline depends on these):
- Every line must start with exactly "Host: " or "Guest: " (word, colon, space, then speech).
- No stage directions, no markdown, no bullet points, no blank lines between turns.
- Do not include any line that does not start with "Host: " or "Guest: ".
- Write entirely in the language of the article unless instructed otherwise."""


def _dialog_openai(
    content: str,
    language: str,
    word_count: int,
    style: str,
    instructions: str | None = None,
) -> tuple[str, dict]:
    from openai import OpenAI
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    lang_instruction = "Write in English." if language == "en" else f"Write in {language}."
    system_content = (
        f"{DIALOG_SYSTEM} {lang_instruction} "
        f"Style: {style}. Target length: {word_count} words."
    )
    if instructions:
        system_content += f"\n\nAdditional instructions:\n{instructions}"
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"Article:\n\n{content[:15000]}"},
        ],
        max_tokens=min(word_count * 3, 8000),
    )
    usage = {
        "input_tokens": resp.usage.prompt_tokens if resp.usage else None,
        "output_tokens": resp.usage.completion_tokens if resp.usage else None,
        "total_tokens": resp.usage.total_tokens if resp.usage else None,
    }
    return (resp.choices[0].message.content or "").strip(), usage


def _dialog_google(
    content: str,
    language: str,
    word_count: int,
    style: str,
    instructions: str | None = None,
) -> tuple[str, dict]:
    from google import genai
    from google.genai import types
    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)
    lang_instruction = "Write in English." if language == "en" else f"Write in {language}."
    prompt = (
        f"{DIALOG_SYSTEM} {lang_instruction} Style: {style}. Target length: {word_count} words."
    )
    if instructions:
        prompt += f"\n\nAdditional instructions:\n{instructions}"
    prompt += f"\n\nArticle:\n\n{content[:15000]}\n\nDialogue:"
    r = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    usage = {
        "input_tokens": r.usage_metadata.prompt_token_count,
        "output_tokens": r.usage_metadata.candidates_token_count,
        "total_tokens": r.usage_metadata.total_token_count,
    }
    return (r.text or "").strip(), usage


def _tts_gemini_multispeaker(
    transcript: str,
    out_path: str,
    voice1: str,
    voice2: str,
    tts_model: str,
    language: str,
) -> dict:
    """Send transcript to Gemini multi-speaker TTS. Chunks if needed, concatenates with pydub."""
    from google import genai
    from google.genai import types
    from pydub import AudioSegment

    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)
    lang_code = to_bcp47(language)

    tts_config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                speaker_voice_configs=[
                    types.SpeakerVoiceConfig(
                        speaker="Host",
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice1)
                        ),
                    ),
                    types.SpeakerVoiceConfig(
                        speaker="Guest",
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice2)
                        ),
                    ),
                ]
            ),
            language_code=lang_code,
        ),
    )

    # Split transcript into chunks of ~3000 chars at turn boundaries to stay within API limits
    chunks = _chunk_transcript(transcript, max_chars=3000)
    segments: list[AudioSegment] = []
    total_input = 0
    total_output = 0
    total_tokens = 0

    for chunk in chunks:
        response = client.models.generate_content(
            model=tts_model,
            contents=chunk,
            config=tts_config,
        )
        audio_bytes = response.candidates[0].content.parts[0].inline_data.data
        seg = AudioSegment(data=audio_bytes, sample_width=2, frame_rate=24000, channels=1)
        segments.append(seg)
        if response.usage_metadata:
            total_input += response.usage_metadata.prompt_token_count or 0
            total_output += response.usage_metadata.candidates_token_count or 0
            total_tokens += response.usage_metadata.total_token_count or 0

    combined = segments[0]
    for seg in segments[1:]:
        combined = combined + seg
    combined.export(out_path, format="mp3")

    return {
        "input_tokens": total_input or None,
        "output_tokens": total_output or None,
        "total_tokens": total_tokens or None,
        "input_characters": None,
    }


def _tts_openai_turns(
    transcript: str,
    out_path: str,
    voice1: str,
    voice2: str,
) -> dict:
    """Fallback TTS for tts_provider=openai: one call per turn, concatenated."""
    from openai import OpenAI
    from pydub import AudioSegment
    import io

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    segments: list[AudioSegment] = []
    total_chars = 0

    for line in transcript.splitlines():
        line = line.strip()
        if line.startswith("Host: "):
            voice = voice1
            text = line[6:]
        elif line.startswith("Guest: "):
            voice = voice2
            text = line[7:]
        else:
            continue
        if not text:
            continue
        total_chars += len(text)
        with client.audio.speech.with_streaming_response.create(
            model="tts-1-hd",
            voice=voice,
            input=text[:4096],
        ) as response:
            buf = io.BytesIO(response.read())
        segments.append(AudioSegment.from_mp3(buf))

    if not segments:
        raise ValueError("No dialogue turns found in transcript")

    pause = AudioSegment.silent(duration=200)
    combined = segments[0]
    for seg in segments[1:]:
        combined = combined + pause + seg
    combined.export(out_path, format="mp3")

    return {"input_characters": total_chars, "input_tokens": None, "output_tokens": None, "total_tokens": None}


def _chunk_transcript(transcript: str, max_chars: int = 3000) -> list[str]:
    """Split transcript into chunks at turn boundaries without exceeding max_chars."""
    lines = [l for l in transcript.splitlines() if l.strip().startswith(("Host: ", "Guest: "))]
    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for line in lines:
        if current_len + len(line) + 1 > max_chars and current_lines:
            chunks.append("\n".join(current_lines))
            current_lines = []
            current_len = 0
        current_lines.append(line)
        current_len += len(line) + 1

    if current_lines:
        chunks.append("\n".join(current_lines))

    if not chunks:
        raise ValueError(
            "No dialogue turns found in transcript — expected lines starting with 'Host: ' or 'Guest: '"
        )
    return chunks


async def generate_podcast_audio(
    content: str,
    *,
    language: str = "en",
    word_count: int = 600,
    style: str = "engaging,fast-paced",
    voice1: str = "Puck",
    voice2: str = "Charon",
    openai_voice1: str = "alloy",
    openai_voice2: str = "echo",
    google_tts_model: str = "gemini-2.5-flash-preview-tts",
    instructions: str | None = None,
) -> tuple[str, dict]:
    """Strip HTML → LLM dialogue → TTS → MP3. Returns (path, token_usage)."""
    settings = get_settings()
    plain = strip_html(content)
    if not plain.strip():
        raise ValueError("Content is empty after stripping HTML")

    os.makedirs(_TMP_DIR, exist_ok=True)
    out_path = os.path.join(_TMP_DIR, f"podcast_{uuid.uuid4().hex}.mp3")

    if settings.llm_provider == "openai":
        transcript, llm_usage = _dialog_openai(
            plain, language, word_count, style, instructions
        )
    else:
        transcript, llm_usage = _dialog_google(
            plain, language, word_count, style, instructions
        )

    if not transcript.strip():
        raise ValueError("LLM returned an empty transcript")

    if settings.tts_provider == "google":
        tts_usage = _tts_gemini_multispeaker(transcript, out_path, voice1, voice2, google_tts_model, language)
    else:
        tts_usage = _tts_openai_turns(transcript, out_path, voice1=openai_voice1, voice2=openai_voice2)

    return out_path, {"llm": llm_usage, "tts": tts_usage}
