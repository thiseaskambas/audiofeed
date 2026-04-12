"""FastAPI app: lifespan startup validation + provider config, health."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from arq import create_pool, Worker
from arq.connections import RedisSettings

from app.config import get_settings
from app.routes import generate
from app.jobs import init_redis

_OPENAPI_YAML = Path(__file__).parent.parent / "openapi.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_for_startup()

    # Connect to Redis — fail fast if misconfigured
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.ping()
    except Exception as exc:
        await pool.close()
        raise RuntimeError(f"Cannot connect to Redis at {settings.redis_url}: {exc}") from exc
    init_redis(pool)

    # Ensure audio tmp dir exists (relative to CWD, which is /app in Docker)
    os.makedirs("data/audio/tmp", exist_ok=True)

    # Expose GEMINI_API_KEY via env so google-genai clients can pick it up automatically.
    if settings.google_api_key:
        os.environ["GEMINI_API_KEY"] = settings.google_api_key

    # Start the ARQ worker in the same process (same pattern as BullMQ in Node.js)
    # handle_signals=False: let uvicorn own SIGINT/SIGTERM, not the ARQ worker
    from app.worker import WorkerSettings
    worker = Worker(
        functions=WorkerSettings.functions,
        on_startup=WorkerSettings.on_startup,
        redis_settings=WorkerSettings.redis_settings,
        job_timeout=WorkerSettings.job_timeout,
        keep_result=WorkerSettings.keep_result,
        max_tries=WorkerSettings.max_tries,
        handle_signals=False,
    )
    worker_task = asyncio.create_task(worker.async_run())

    yield

    worker_task.cancel()
    try:
        await worker_task
    except (asyncio.CancelledError, Exception):
        pass
    finally:
        await worker.close()
        await pool.close()


app = FastAPI(
    title="Audiofeed",
    description="Article → audio generation (podcast, narration, Instagram voiceover)",
    version="0.1.0",
    lifespan=lifespan,
    # Disable auto-generated docs — we serve the hand-crafted openapi.yaml instead
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(generate.router, prefix="", tags=["generate"])


@app.get("/openapi.yaml", include_in_schema=False)
def serve_openapi_yaml():
    return FileResponse(_OPENAPI_YAML, media_type="application/yaml")


@app.get("/docs", include_in_schema=False)
def swagger_ui():
    return HTMLResponse("""<!DOCTYPE html>
<html>
<head>
  <title>Audiofeed API</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({
      url: "/openapi.yaml",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
      layout: "BaseLayout",
      deepLinking: true,
    });
  </script>
</body>
</html>
""")


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=True,
    )
