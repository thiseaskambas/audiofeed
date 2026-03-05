# Audiofeed — Python microservice (no Playwright in image to save ~300MB)
FROM python:3.12-slim

WORKDIR /app

# System deps for podcastfy (ffmpeg) and build
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
# Ensure podcastfy output dir exists
RUN mkdir -p data/audio/tmp data/transcripts

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
