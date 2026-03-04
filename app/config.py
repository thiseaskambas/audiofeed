"""Load and validate settings from environment."""

from __future__ import annotations

import os
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

    # Provider: "openai" or "google" (LLM + TTS)
    provider: Provider = "openai"

    # OpenAI (required if provider=openai)
    openai_api_key: str | None = None

    # Google (required if provider=google)
    google_api_key: str | None = None
    google_application_credentials: str | None = None

    # Sevalla S3
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_name: str = "audiofeed-audio"

    # Shared secret for X-API-Key
    api_secret: str = ""

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    def validate_for_startup(self) -> None:
        """Raise ValueError if required env vars for current provider are missing."""
        if self.provider == "openai":
            if not (self.openai_api_key and self.openai_api_key.startswith("sk-")):
                raise ValueError(
                    "PROVIDER=openai requires OPENAI_API_KEY to be set (starts with sk-)"
                )
        elif self.provider == "google":
            if not self.google_api_key:
                raise ValueError("PROVIDER=google requires GOOGLE_API_KEY to be set")
            if not self.google_application_credentials or not os.path.isfile(
                self.google_application_credentials
            ):
                raise ValueError(
                    "PROVIDER=google requires GOOGLE_APPLICATION_CREDENTIALS to point to a valid JSON file"
                )
        else:
            raise ValueError('PROVIDER must be "openai" or "google"')

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
