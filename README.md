# Alcohol Label Verification App

A stateless decision-support prototype for comparing alcohol-label artwork with structured
application values. OpenAI vision extracts observable label text, deterministic rules compare it
with the application, and a human reviewer makes the final approval or rejection decision.

The prototype supports a preprocessed Reviewer Hub, one-off application intake, and CSV-based batch
intake. It uses server memory rather than a database, so queue contents, batch progress, decisions,
and comments reset whenever the backend restarts or a hosted instance spins down.

## Repository layout

```text
frontend/   React and strict TypeScript browser application
backend/    FastAPI API, OCR adapter, comparison engine, and queue services
fixtures/   Synthetic applications, extraction scenarios, and label images
contracts/  Generated JSON Schema shared by the backend and frontend
adr/        Architectural decision records
docs/       Product source material, requirements, and data-model documentation
```

## Prerequisites

- Node.js 22.12 or newer
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker, only when using the container or hosted deployment workflow

## Quick start with mock OCR

Mock mode requires no OpenAI API key and is the recommended way to inspect the UI and failure
states locally.

1. Create a local `.env` file in the repository root:

   ```dotenv
   APP_ENVIRONMENT=test
   OCR_PROVIDER=mock
   OPENAI_OCR_MODEL=gpt-4o-mini
   OPENAI_IMAGE_DETAIL=high
   OPENAI_OCR_TIMEOUT_SECONDS=300
   ```

2. Install and start the backend:

   ```bash
   cd backend
   uv sync
   uv run uvicorn app.main:app --app-dir src --reload --port 8000
   ```

3. In another terminal, install and start the frontend with mock controls visible:

   ```bash
   cd frontend
   npm ci
   VITE_ENABLE_OCR_MOCK_CONTROLS=true npm run dev
   ```

4. Open `http://localhost:5173`.

Vite proxies `/health` and `/api` to the backend on port 8000. FastAPI documentation is available
at `http://localhost:8000/api/docs`.

## Running with live OpenAI OCR

Set the root `.env` to use the OpenAI provider, then restart the backend:

```dotenv
APP_ENVIRONMENT=development
OCR_PROVIDER=openai
OPENAI_API_KEY=replace-with-your-key
OPENAI_OCR_MODEL=gpt-4o-mini
OPENAI_IMAGE_DETAIL=high
OPENAI_OCR_TIMEOUT_SECONDS=300
```

Start the frontend normally so mock scenario controls are not included:

```bash
cd frontend
npm run dev
```

The API key is read only by the backend. Do not commit `.env`; it is ignored by Git.

## How to use the application

The home screen provides three workflows.

### Reviewer Hub

Reviewer Hub is the primary human-review workflow.

1. Select **Open Reviewer Hub**.
2. Search or filter the temporary queue and select an application.
3. Review the expected application values, submitted label, automated status, and field-level
   comparison findings.
4. Optionally enter a reviewer comment.
5. Select **Approve application** or **Reject application**.
6. Use **Undo** within ten seconds if the decision was accidental.

Green queue entries have no automated discrepancies. Yellow entries need human attention.
`Analysis incomplete` is presented as review needed with an additional explanation in the selected
application. Automated results remain decision support and are not regulatory approval or rejection.

### Single Application Input

Use this secondary workflow for a synthetic demonstration or exceptional one-off intake.

1. Select **Single Application Input**.
2. Enter the expected label values, or select **Load synthetic example**.
3. Continue to the upload step and select one non-empty JPEG or PNG image under 20 MB.
4. Select **Verify label**.
5. Review the OCR and deterministic comparison findings.
6. Select **Review this application now** to open the newly created Reviewer Hub entry.

The government-warning reference is supplied by the versioned server ruleset and is not entered by
the user.

### Batch Application Input

Batch intake accepts one UTF-8 CSV and between 1 and 200 matching JPEG or PNG images.

1. Select **Batch Application Input**.
2. Download the CSV template or use
   [`fixtures/applications/example-reviewer-queue-batch.csv`](fixtures/applications/example-reviewer-queue-batch.csv).
3. Enter one application per row. Every `record_id` and `filename` must be unique.
4. Set `filename` to the exact, case-sensitive basename of the corresponding image.
5. Select the CSV and all referenced images, then select **Validate and process batch**.
6. Watch the ready-for-review counter. Up to three applications process concurrently, and each
   completed result enters Reviewer Hub immediately in CSV order.
7. If processing pauses, retry each failed item, choose a same-named replacement image, or select
   **Skip and continue**. Skipped items do not enter Reviewer Hub.
8. Filter the results, review ready applications, or download the result summary CSV.

For the included batch example, select these images with the example CSV:

- `fixtures/reviewer_queue/01-old-tom-distillery.png`
- `fixtures/reviewer_queue/02-meadowlark-rye.png`

The fixed `success` mock scenario always emits the Old Tom observation set; use live OCR when testing
whether both different images are read accurately. Example batch record IDs can be used once per
backend session unless they are changed or the backend is restarted.

## Supported configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `APP_ENVIRONMENT` | Yes | `development`, `test`, or `production` |
| `OCR_PROVIDER` | No | `openai` by default, or `mock`; mock is prohibited in production |
| `OPENAI_API_KEY` | Live OCR only | Server-side OpenAI credential |
| `OPENAI_OCR_MODEL` | No | Vision model; defaults to `gpt-4o-mini` |
| `OPENAI_IMAGE_DETAIL` | No | `low`, `high`, or `auto`; defaults to `high` |
| `OPENAI_OCR_TIMEOUT_SECONDS` | No | Per-image provider timeout from greater than 0 through 300 seconds |
| `VITE_ENABLE_OCR_MOCK_CONTROLS` | No | Build-time/local frontend flag; set to `true` only for mock demonstrations |

Mock scenario names and expected failure behavior are documented in
[`fixtures/extractions/mock-scenarios.json`](fixtures/extractions/mock-scenarios.json).

## OCR and comparison behavior

`POST /api/extractions` accepts a serialized `VerificationSubmission` and its ordered image files as
`multipart/form-data`. The backend validates actual JPEG/PNG content, applies orientation, strips
metadata, downsizes oversized images, and compresses them in memory before OCR. It does not write
uploaded images to disk.

OpenAI extracts observations only. The deterministic comparison engine evaluates brand, class/type,
alcohol content where applicable, net contents, bottler/producer name and address, imported-product
origin, and the versioned government warning. The result retains expected values, detected values,
normalization, evidence, and applied rule identifiers for human review.

To run an opt-in live benchmark using synthetic or public data:

```bash
cd backend
OCR_PROVIDER=openai uv run python -m app.extraction.benchmark \
  --image ../path/to/synthetic-label.jpg --runs 1
```

This command can make a paid OpenAI request. It reports safe compression and timing metrics without
printing image content, extracted text, prompts, credentials, or provider bodies.

## Run the test suite

Backend:

```bash
cd backend
uv run ruff check src tests
uv run pytest
```

Frontend:

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

## Build and run with Docker

The Docker image builds the React application and serves it from the FastAPI process as a
single-origin deployment.

1. Build the image from the repository root:

   ```bash
   docker build -t alcohol-label-verification-app .
   ```

2. Create a root `.env` configured for the container:

   ```dotenv
   APP_ENVIRONMENT=production
   OCR_PROVIDER=openai
   OPENAI_API_KEY=replace-with-your-key
   OPENAI_OCR_MODEL=gpt-4o-mini
   OPENAI_IMAGE_DETAIL=high
   OPENAI_OCR_TIMEOUT_SECONDS=300
   ```

3. Start the container:

   ```bash
   docker run --rm --env-file .env -p 8000:8000 alcohol-label-verification-app
   ```

4. Open `http://localhost:8000` and verify health:

   ```bash
   curl --fail http://localhost:8000/health
   ```

Expected response:

```json
{"status":"ok","service":"alcohol-label-verification-api"}
```

## Deploy to Render

[`render.yaml`](render.yaml) defines a free-tier Docker web service, the Dockerfile path, health
check, production environment, OpenAI provider, and model settings. Render documents this workflow
as [Blueprint infrastructure as code](https://render.com/docs/infrastructure-as-code).

1. Push the desired branch to a GitHub repository accessible to Render.
2. Sign in to Render and select **New > Blueprint**.
3. Connect the GitHub repository and select the repository containing this `render.yaml`.
4. Review the proposed `alcohol-label-verification-app` web service.
5. Enter `OPENAI_API_KEY` when Render prompts for the unsynchronized secret.
6. Apply the Blueprint and wait for the Docker build and health check to complete.
7. Open the generated `https://<service-name>.onrender.com` URL.
8. Confirm `https://<service-name>.onrender.com/health` returns the expected health response.

The Blueprint currently sets `OPENAI_OCR_TIMEOUT_SECONDS` to 4 seconds. If representative labels
cannot complete within that window, change the environment variable in Render to the measured demo
timeout and redeploy. Configuration changes require a service restart.

Render currently spins down a free web service after 15 minutes without inbound traffic. A cold
start can delay the next request, and every sleep, restart, or redeployment clears the in-memory
Reviewer Hub and batch state. See [Render's free-service limitations](https://render.com/docs/free)
for current details. Free hosting is suitable for this shareholder prototype, not for persistent or
multi-reviewer production use.

## Data-model contracts

Backend Pydantic models are the source of truth for API contracts. After changing a boundary model,
regenerate the committed JSON Schema and TypeScript declarations:

```bash
cd backend
uv run python scripts/export_contract.py

cd ../frontend
npm run generate:contracts
```

See [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) for the model and data-flow specification and
[`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) for product requirements.

No PostgreSQL or other database is required for the current prototype.
