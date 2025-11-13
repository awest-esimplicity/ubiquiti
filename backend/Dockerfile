# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
COPY frontend/scripts ./scripts
ENV HUSKY=0
RUN npm install

COPY frontend/ ./
RUN npm run build

# ----------------------------------------------------------------------
# Backend build stage: install Python deps (with build tooling available)
# ----------------------------------------------------------------------
FROM python:3.13-slim AS backend-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    UV_PROJECT_ENV=/app/.venv

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install uv==0.4.18

COPY backend/src ./src
RUN uv sync --frozen --project .

# ----------------------------------------------------------------------
# Runtime image
# ----------------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENV=/app/.venv \
    PATH="/app/.venv/bin:${PATH}" \
    UBIQUITI_DB_URL=""

WORKDIR /app

COPY --from=backend-builder /app/.venv /app/.venv
COPY backend/src ./src
COPY backend/pyproject.toml backend/uv.lock ./ 
COPY backend/README.md ./README.md
COPY streamlit_app.py ./streamlit_app.py
COPY devices.txt ./devices.txt
RUN mkdir -p frontend/dist
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["uv", "run", "--project", ".", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
