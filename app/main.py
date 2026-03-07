"""FastAPI app: lifespan startup validation + provider config, health."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

from app.config import get_settings
from app.routes import generate

_OPENAPI_YAML = Path(__file__).parent.parent / "openapi.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_for_startup()

    # Ensure podcastfy output dirs exist (relative to CWD, which is /app in Docker)
    os.makedirs("data/audio/tmp", exist_ok=True)
    os.makedirs("data/transcripts", exist_ok=True)

    # Expose keys via env so google clients can pick them up automatically
    if settings.provider == "google" and settings.google_api_key:
        os.environ["GEMINI_API_KEY"] = settings.google_api_key
    if settings.google_application_credentials:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.google_application_credentials

    yield


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
