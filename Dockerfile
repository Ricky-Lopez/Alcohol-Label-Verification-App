FROM node:24-alpine AS frontend-build

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIST_DIR=/app/static \
    PATH=/app/backend/.venv/bin:$PATH

COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project

COPY backend/ ./backend/
RUN cd backend && uv sync --frozen --no-dev

COPY --from=frontend-build /build/frontend/dist ./static

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir backend/src --host 0.0.0.0 --port ${PORT:-8000}"]
