"""Load and validate settings from environment."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


Provider = Literal["openai", "google"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM provider: which model generates dialogue/scripts ("openai" or "google")
    llm_provider: Provider = "openai"
    # TTS provider: which engine synthesises audio ("openai" or "google")
    tts_provider: Provider = "openai"

    # OpenAI (required if llm_provider=openai or tts_provider=openai)
    openai_api_key: str | None = None

    # Google (required if llm_provider=google or tts_provider=google)
    google_api_key: str | None = None

    # NotebookLM Enterprise (required for type="notebooklm_podcast")
    # Auth is via GOOGLE_APPLICATION_CREDENTIALS service account (ADC)
    notebooklm_project_id: str | None = None
    notebooklm_location: str = "global"
    notebooklm_daily_limit: int = 20  # Google's default quota per identity per day

    # Sevalla S3
    s3_endpoint_url: str = ""
    s3_public_url: str = ""  # public base URL for generated audio links (e.g. https://bucket.sevalla.storage)
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_name: str = "audiofeed-audio"

    # Shared secret for X-API-Key
    api_secret: str = ""

    # Server port (used when running via `python -m app.main` or Docker)
    port: int = 8020

    redis_url: str = "redis://localhost:6379"

    @field_validator("llm_provider", "tts_provider", mode="before")
    @classmethod
    def normalize_provider(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    def validate_for_startup(self) -> None:
        """Raise ValueError if required env vars for current providers are missing."""
        needs_openai = self.llm_provider == "openai" or self.tts_provider == "openai"
        needs_google = self.llm_provider == "google" or self.tts_provider == "google"

        if needs_openai:
            if not (self.openai_api_key and self.openai_api_key.startswith("sk-")):
                raise ValueError(
                    "OPENAI_API_KEY must be set (starts with sk-) when LLM_PROVIDER=openai or TTS_PROVIDER=openai"
                )
        if needs_google:
            if not self.google_api_key:
                raise ValueError(
                    "GOOGLE_API_KEY must be set when LLM_PROVIDER=google or TTS_PROVIDER=google"
                )

        if not self.api_secret:
            raise ValueError("API_SECRET must be set (used for X-API-Key header)")

        if not all(
            [self.s3_endpoint_url, self.s3_access_key_id, self.s3_secret_access_key, self.s3_bucket_name]
        ):
            raise ValueError(
                "S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, and S3_BUCKET_NAME must be set"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
