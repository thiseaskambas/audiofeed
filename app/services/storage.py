"""Upload audio file to Sevalla S3 bucket and return public URL."""

from __future__ import annotations

import os
from pathlib import Path

import boto3
from botocore.config import Config

from app.config import get_settings


def upload_audio(
    local_path: str | Path,
    key_prefix: str,
    filename: str | None = None,
) -> str:
    """
    Upload file to S3 and return the public URL.
    key_prefix e.g. "podcast", "narration", "instagram".
    """
    path = Path(local_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")
    name = filename or path.name
    key = f"audiofeed/{key_prefix}/{name}"

    settings = get_settings()
    # Path-style addressing if URLs 404 with default (virtual-hosted)
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=Config(s3={"addressing_style": "path"}),
    )
    client.upload_file(str(path), settings.s3_bucket_name, key)
    # Public URL: endpoint is typically the bucket endpoint, e.g. https://bucket.sevalla.com
    base = settings.s3_endpoint_url.rstrip("/")
    return f"{base}/{key}"
