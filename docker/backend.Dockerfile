FROM ghcr.io/astral-sh/uv:0.4.10-python3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY packages ./packages

RUN uv pip install --system .

ENV RECOZIK_WEB_BASE_MEDIA_ROOT=/data \
    RECOZIK_WEB_UPLOAD_SUBDIR=uploads

EXPOSE 8000

CMD ["uvicorn", "recozik_web.app:app", "--host", "0.0.0.0", "--port", "8000"]
