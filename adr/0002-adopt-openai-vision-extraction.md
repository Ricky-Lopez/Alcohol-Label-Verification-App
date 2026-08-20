# ADR 0002: Adopt OpenAI vision for prototype label extraction

- **Status:** Accepted
- **Date:** 2026-08-19
- **Related requirements:** FR-009, FR-016–FR-019, NFR-001–NFR-005, SEC-001–SEC-008

## Context

The prototype needs bounded, structured extraction from synthetic alcohol-label images. It must
preserve warning wording, reject unrelated images, remain testable without credentials, and avoid
inventing confidence or evidence geometry. Image analysis must stay separate from deterministic
regulatory comparison.

## Decision

Use the OpenAI Responses API with `gpt-4o-mini`, high image detail, Structured Outputs, stateless
requests, a four-second per-image timeout, and SDK retries disabled. Access it through an internal
provider interface with a deterministic mock implementation.

Before provider submission, validate JPEG/PNG content and metadata, apply orientation, strip
metadata, cap the longest edge at 2048 pixels, and re-encode in memory. Never persist image bytes or
include extracted content in logs.

The provider prompt receives no expected application or authoritative warning values. Warning text
is transcribed as visible and is not normalized. Confidence and image regions remain optional
because the selected provider does not return calibrated OCR confidence or guaranteed geometry.

Non-label, uncertain, timeout, refusal, and invalid-response outcomes are represented explicitly.
The mock provider is available only outside production and returns the same public contract as the
OpenAI implementation.

## Consequences

- The backend requires outbound access to `api.openai.com` for live extraction.
- Live behavior depends on a server-side `OPENAI_API_KEY`; health and mock testing do not.
- Compression lowers payload size but may affect small text, so the policy must be benchmarked on
  representative synthetic warning labels before production use.
- OpenAI output remains probabilistic evidence. Only deterministic rules may report comparisons,
  and human review remains authoritative.
