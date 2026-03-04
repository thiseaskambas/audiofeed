"""Strip HTML to plain text (BeautifulSoup) + language code helpers."""

from __future__ import annotations

from bs4 import BeautifulSoup

# Maps ISO 639-1 codes → BCP-47 codes for Google Cloud TTS
_LANG_CODE_MAP: dict[str, str] = {
    "en": "en-US",
    "es": "es-ES",
    "fr": "fr-FR",
    "de": "de-DE",
    "it": "it-IT",
    "pt": "pt-BR",
    "nl": "nl-NL",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "zh": "cmn-CN",
    "ar": "ar-XA",
    "hi": "hi-IN",
    "ru": "ru-RU",
    "pl": "pl-PL",
    "tr": "tr-TR",
    "el": "el-GR",
}


def to_bcp47(lang: str) -> str:
    """Convert an ISO 639-1 code to a BCP-47 tag accepted by Google Cloud TTS."""
    return _LANG_CODE_MAP.get(lang.lower(), f"{lang}-{lang.upper()}")


def strip_html(html_or_text: str) -> str:
    """Extract plain text from HTML or return as-is if no tags."""
    if not html_or_text or not html_or_text.strip():
        return ""
    soup = BeautifulSoup(html_or_text, "html.parser")
    return soup.get_text(separator=" ", strip=True)
