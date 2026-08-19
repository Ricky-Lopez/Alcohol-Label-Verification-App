# ADR 0001: Adopt React, Vite, and FastAPI for the prototype

- **Status:** Accepted
- **Date:** 2026-08-19
- **Decision owners:** Project team
- **Related requirements:** [Alcohol Label Verification Web Application Requirements](../docs/REQUIREMENTS.md)

## Context

The project needs a standalone web application that helps compliance agents compare alcohol-label
artwork with structured application values. The prototype must:

- return usable single-label results in about five seconds under documented test conditions;
- provide a simple, accessible interface for users with widely varying technical comfort;
- accept image uploads and present field-level text and visual evidence;
- support OCR, image analysis, and deterministic comparison rules;
- operate without direct COLA integration;
- avoid required browser calls to blocked third-party domains;
- use only synthetic or public data for the prototype; and
- leave room for a session-scoped batch review queue without requiring a database.

The primary technical uncertainty is OCR accuracy and latency on realistic label images. Server-side
rendering, search-engine optimization, persistent accounts, and durable workflow history are not
core prototype needs.

## Decision

We will use a React and strict TypeScript frontend built with Vite, backed by a Python FastAPI API.
The frontend and backend will be separate build units in one repository but will initially be
packaged as one deployable container and exposed through one origin.

### Frontend

- Use React with strict TypeScript.
- Use Vite for local development and production builds.
- Use native semantic HTML wherever practical.
- Use CSS Modules and shared design tokens for styling rather than adopting a large component or
  styling framework at project start.
- Use Vitest and Testing Library for component and interaction tests.
- Use Playwright for critical browser workflows.

The frontend will own:

- selection of preloaded synthetic application records;
- ad hoc synthetic application entry;
- label upload, preview, replacement, and removal;
- progress, safe error, and timeout states;
- field-level comparison results and image evidence;
- accessibility behavior; and
- the future session-scoped batch review queue.

### Backend

- Use Python and FastAPI for the HTTP API.
- Use Pydantic models as the authoritative API request and response schemas.
- Generate or validate TypeScript client types from the FastAPI OpenAPI contract rather than
  maintaining unrelated handwritten schemas.
- Use pytest for unit, contract, integration, and performance-oriented backend tests.
- Keep upload validation, extraction, normalization, comparison, and result assembly in separate
  modules.

The backend will own:

- server-side input and file validation;
- bounded temporary handling of uploaded images;
- OCR and image-analysis orchestration;
- deterministic brand, alcohol-content, and warning checks;
- ruleset and extractor-version reporting;
- confidence and evidence mapping;
- sanitized operational metrics and errors; and
- session-scoped batch processing when P1 is implemented.

### OCR and image analysis

OCR will be accessed through an internal adapter rather than directly from route handlers or UI
code. The application contract will return recognized text, confidence, and source regions without
exposing an engine-specific response.

PaddleOCR and Tesseract are initial candidates, not selected dependencies. We will run a focused
spike against the synthetic label corpus before choosing the first implementation. The spike must
measure warmed and cold-start latency, text accuracy, bounding-region quality, packaging size,
offline operation, and deployment compatibility.

Model artifacts required at runtime must be included in the build or provisioned during an approved
deployment step. The application must not depend on downloading models from the browser or from an
unapproved host during verification. Warning-heading boldness will remain a separate visual-analysis
concern because recognized text alone is not sufficient evidence of font weight.

### State and persistence

- P0 will use version-controlled JSON or equivalent synthetic fixtures and request- or
  session-scoped state.
- P1 batch processing will remain session-scoped and must clearly warn that unfinished work can be
  lost when the session expires or the process restarts.
- PostgreSQL, another relational database, or a durable job broker will not be required for P0 or
  P1.
- Durable batch recovery, cross-session history, multi-user assignment, and persistent audit data
  are stretch or future-production capabilities. Introducing a database for any of these requires a
  separate ADR covering retention, deletion, security, migrations, and operations.

### Repository structure

We will start with direct, descriptive top-level directory names:

```text
frontend/
  src/
    api/
    components/
    features/
    styles/
  tests/

backend/
  src/
    api/
    comparison/
    extraction/
    models/
    rules/
  tests/

contracts/
fixtures/
  applications/
  labels/
adr/
docs/
```

We prefer `frontend/` and `backend/` over `apps/` and `services/` while the repository contains only
one browser application and one API. The structure may be revisited if the repository gains multiple
independently deployed applications or services.

### Packaging and deployment

- Use Docker to provide a reproducible runtime for the API and OCR dependencies.
- Build the Vite application into static assets during the container build.
- Serve the compiled frontend and `/api/*` from the same deployed origin, either directly through
  FastAPI or through a minimal same-container web-serving layer if measurements justify it.
- Keep local development convenient by running Vite and FastAPI as separate development processes.
- Do not select a specific cloud hosting product in this ADR.

## Alternatives considered

### Next.js with a Python analysis service

Not selected because the prototype does not need server-side rendering or search indexing and would
still require Python for the likely OCR and image-processing path. This would add a second server
framework without a demonstrated requirement.

### TypeScript-only frontend and backend

Not selected because it would constrain OCR and computer-vision choices or require wrapping Python
tools as subprocesses. It remains viable if the OCR spike selects a sufficiently capable external
or JavaScript-native engine and restricted-network requirements are still met.

### FastAPI with server-rendered templates

Not selected because the evidence viewer, interactive form states, and future batch queue benefit
from a dedicated client application. This option would reduce frontend tooling but make the richer
review workflow less straightforward.

### Streamlit or Gradio

Not selected as the application shell because the project requires deliberate accessibility,
interaction, validation, error handling, and visual-evidence behavior. These tools may still be
useful for an isolated OCR experiment outside the delivered application.

### Database-backed workflow from the start

Not selected because P0 requires neither durable records nor user accounts. Adding a database now
would introduce schema, migration, retention, security, and deployment work before it provides user
value.

## Consequences

### Positive

- React supports the interactive evidence and queue experience while TypeScript makes UI and API
  states explicit.
- Python provides direct access to mature OCR and image-processing tools.
- FastAPI provides typed validation and an OpenAPI contract suitable for generating frontend types.
- A single-origin deployment avoids routine CORS configuration and reduces browser-visible network
  dependencies.
- The OCR adapter keeps engine selection reversible and independently testable.
- Avoiding a database keeps the first implementation focused on verification quality and latency.

### Negative and trade-offs

- The project has two language toolchains and two dependency ecosystems.
- API contract generation or validation becomes a required build concern.
- Bundled OCR models can increase container size and startup time.
- Session-scoped batches cannot survive restart or support cross-session history.
- Serving the frontend through the API process is simple but may be less efficient than a dedicated
  static host at larger scale; that scale is outside the prototype.
- Python OCR work can block an event loop if implemented directly in asynchronous route handlers,
  so inference must run through an appropriate bounded execution path.

## Verification and follow-up decisions

Before treating the scaffold as validated, the team will:

1. Create a minimal vertical slice from label upload through a typed API response to rendered
   evidence.
2. Benchmark candidate OCR engines against representative synthetic labels.
3. Confirm that the warmed verification path can meet the documented five-second target.
4. Confirm keyboard operation, focus behavior, status announcements, 200% zoom, and non-color-only
   result indicators in the vertical slice.
5. Confirm that the packaged application runs without runtime model downloads or undeclared browser
   dependencies.
6. Record the selected OCR engine and preprocessing strategy in a separate ADR after the spike.
7. Record a separate persistence ADR only if a stretch or production requirement justifies durable
   storage.
