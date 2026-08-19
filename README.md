# Alcohol Label Verification App

A standalone prototype that will help compliance agents compare alcohol-label artwork with
structured application values. The current slice establishes the React/Vite frontend, FastAPI
backend, health check, test configuration, and local/container deployment path.

## Repository layout

```text
frontend/   React and strict TypeScript browser application
backend/    FastAPI service and verification modules
fixtures/   Synthetic application and label inputs (added with verification slices)
contracts/  Generated frontend-to-engine contract schema
adr/        Architectural decision records
docs/       Product source material and requirements
```

## Prerequisites

- Node.js 22.12 or newer
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose, if using the container workflow

## Local development

Create a local `.env` file in the repository root. It is ignored by Git and must never be
committed. The application recognizes these variables:

| Variable | Required now | Purpose |
| --- | --- | --- |
| `APP_ENVIRONMENT` | Yes | Runtime mode: `development`, `test`, or `production` |
| `OCR_API_KEY` | No | Reserved for the future OCR adapter; leave unset until a provider is selected |

Never place a real OCR API key in source files, documentation, Docker images, or Git history.

Install and start the API:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --app-dir src --reload --port 8000
```

In another terminal, install and start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/health` to the API on port 8000.

## Verification

Run backend checks:

```bash
cd backend
uv run pytest
uv run ruff check .
```

Run frontend checks:

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

## Data-model contracts

Backend Pydantic models are the source of truth for frontend input, OCR extraction, comparison, and
verification-result types. After changing a boundary model, regenerate the committed JSON Schema
and TypeScript declarations:

```bash
cd backend
uv run python scripts/export_contract.py

cd ../frontend
npm run generate:contracts
```

See [docs/DATA_MODEL.md](docs/DATA_MODEL.md) for the model and data-flow specification.

## Container workflow

Build and run the same single-origin artifact intended for hosting:

```bash
docker compose up --build
```

Then open `http://localhost:8000` or request the health endpoint directly:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok","service":"alcohol-label-verification-api"}
```

## Render preparation

The root `render.yaml` defines one Docker web service using `/health` as its health check. During
initial Blueprint creation, Render prompts for the `OCR_API_KEY` because it is declared with
`sync: false`. Leave it empty until an OCR provider is selected.

Free Render web services can spin down when idle, so cold-start behavior must be measured separately
from the application's warmed five-second verification target. Free hosting is suitable for the
shareholder prototype, not for production use.

No database is required for the P0 or P1 application slices.
