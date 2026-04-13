"""NotebookLM Enterprise Podcast API integration.

End-to-end podcast generation: submits content to Google's NotebookLM API,
polls the resulting long-running operation, and downloads the finished MP3.

Authentication uses Application Default Credentials (ADC) — set
GOOGLE_APPLICATION_CREDENTIALS to a service account JSON with the
roles/discoveryengine.podcastApiUser IAM role assigned.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import google.auth
import google.auth.transport.requests
import httpx

from app.config import get_settings
from app.jobs import get_redis
from app.services.html_utils import strip_html, to_bcp47

logger = logging.getLogger(__name__)

_BASE_URL = "https://discoveryengine.googleapis.com/v1alpha"
_POLL_INTERVAL = 10   # seconds between status polls
_MAX_POLLS = 60       # 10 minutes max (60 × 10s)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_access_token() -> str:
    """Return a fresh OAuth2 bearer token via Application Default Credentials.

    Blocking — run via run_in_executor to avoid stalling the event loop.
    """
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_request = google.auth.transport.requests.Request()
    credentials.refresh(auth_request)
    return credentials.token  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Rate limit guard
# ---------------------------------------------------------------------------

async def _check_and_increment_rate_limit() -> None:
    """Atomically increment the daily usage counter and raise if quota exceeded.

    Key format: notebooklm:daily_usage:{YYYY-MM-DD} (UTC).
    TTL is 25 hours so the key expires safely after the day rolls over.
    """
    settings = get_settings()
    redis = get_redis()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    key = f"notebooklm:daily_usage:{today}"

    # INCR is atomic — increment first, then check
    count = await redis.incr(key)
    await redis.expire(key, 90_000)  # 25 hours

    if count > settings.notebooklm_daily_limit:
        raise RuntimeError(
            f"NotebookLM daily quota exceeded "
            f"({count - 1}/{settings.notebooklm_daily_limit} podcasts already generated today)"
        )


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

async def _submit_podcast_job(
    text: str,
    language_bcp47: str,
    length: str,
    focus: str | None,
    token: str,
) -> str:
    """POST a podcast generation request and return the operation name."""
    settings = get_settings()
    if not settings.notebooklm_project_id:
        raise RuntimeError(
            "NOTEBOOKLM_PROJECT_ID must be set to use type='notebooklm_podcast'"
        )

    url = (
        f"{_BASE_URL}/projects/{settings.notebooklm_project_id}"
        f"/locations/{settings.notebooklm_location}:generatePodcast"
    )
    body: dict[str, Any] = {
        "contexts": [{"text": text}],
        "length": length,
        "language": language_bcp47,
    }
    if focus:
        body["focus"] = focus

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    operation_name = data.get("name")
    if not operation_name:
        raise RuntimeError(
            f"NotebookLM API did not return an operation name. Response: {data}"
        )
    return operation_name


async def _poll_operation(operation_name: str, token: str) -> dict[str, Any]:
    """Poll the long-running operation until done or timeout.

    Raises TimeoutError after _MAX_POLLS × _POLL_INTERVAL seconds.
    Raises RuntimeError if the operation itself reports an error.
    """
    url = f"{_BASE_URL}/{operation_name}"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(_MAX_POLLS):
            if attempt > 0:
                await asyncio.sleep(_POLL_INTERVAL)
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("done"):
                if "error" in data:
                    err = data["error"]
                    raise RuntimeError(
                        f"NotebookLM operation failed: {err.get('message', err)}"
                    )
                return data

    raise TimeoutError(
        f"NotebookLM operation '{operation_name}' did not complete within "
        f"{_MAX_POLLS * _POLL_INTERVAL}s"
    )


async def _download_audio(operation_name: str, token: str, out_path: str) -> None:
    """Stream the completed podcast MP3 to out_path."""
    url = f"{_BASE_URL}/{operation_name}:download?alt=media"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        async with client.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            with open(out_path, "wb") as fh:
                async for chunk in resp.aiter_bytes(chunk_size=65_536):
                    fh.write(chunk)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def generate_notebooklm_podcast(
    content: str,
    *,
    language: str = "en",
    length: str = "STANDARD",
    focus: str | None = None,
    job_id: str,
) -> tuple[str, dict]:
    """Generate a podcast via the NotebookLM Enterprise API.

    Returns (temp_mp3_path, token_usage_dict). The caller is responsible for
    uploading the file to S3 and deleting the temp file afterwards.
    """
    os.makedirs("/data/audio/tmp", exist_ok=True)
    out_path = f"/data/audio/tmp/notebooklm_{job_id}.mp3"

    # 1. Strip HTML and map language code
    text = strip_html(content)
    language_bcp47 = to_bcp47(language)

    # 2. Guard against exceeding the daily quota before making any API call
    await _check_and_increment_rate_limit()

    # 3. Obtain a fresh access token (blocking I/O — offload to thread)
    loop = asyncio.get_event_loop()
    token = await loop.run_in_executor(None, _get_access_token)

    # 4. Submit the podcast generation job
    logger.info("Submitting NotebookLM podcast job=%s length=%s lang=%s", job_id, length, language_bcp47)
    operation_name = await _submit_podcast_job(text, language_bcp47, length, focus, token)
    logger.info("NotebookLM operation started: %s", operation_name)

    # 5. Poll until the operation completes
    await _poll_operation(operation_name, token)
    logger.info("NotebookLM operation completed: %s", operation_name)

    # 6. Download the finished MP3
    await _download_audio(operation_name, token, out_path)

    token_usage = {"notebooklm": {"operation": operation_name}}
    return out_path, token_usage
