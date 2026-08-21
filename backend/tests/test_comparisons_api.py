import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.extraction import (
    ExtractionStatus,
    ExtractionTiming,
    ExtractorReference,
    OcrExtractionResult,
)
from app.models.label import VerificationSubmission
from app.models.verification import ComparisonRequest
from app.rules import PROTOTYPE_RULESET_ID, PROTOTYPE_RULESET_VERSION

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SUBMISSION_PATH = (
    REPOSITORY_ROOT / "fixtures" / "applications" / "example-distilled-spirits-submission.json"
)


def request() -> ComparisonRequest:
    submission = VerificationSubmission.model_validate_json(
        SUBMISSION_PATH.read_text(encoding="utf-8")
    )
    extraction = OcrExtractionResult(
        extraction_id="extraction-1",
        submission_id=submission.submission_id,
        status=ExtractionStatus.FAILED,
        extractor=ExtractorReference(name="mock", version="1"),
        duration_ms=1,
        timing=ExtractionTiming(image_preparation_ms=0, provider_ms=1),
    )
    return ComparisonRequest(
        comparison_id="comparison-1", submission=submission, extraction=extraction
    )


@pytest.mark.anyio
async def test_comparison_route_uses_the_server_owned_ruleset() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/comparisons", json=request().model_dump(mode="json", by_alias=True)
        )

    assert response.status_code == 200
    assert response.json()["ruleset"] == {
        "rulesetId": PROTOTYPE_RULESET_ID,
        "version": PROTOTYPE_RULESET_VERSION,
        "effectiveDate": "2026-08-20",
        "sourceUri": "docs/REQUIREMENTS.md#fr-016",
    }
    assert response.json()["overallStatus"] == "analysis_incomplete"


@pytest.mark.anyio
async def test_comparison_route_rejects_mismatched_submission_ids() -> None:
    body = request().model_dump(mode="json", by_alias=True)
    body["extraction"]["submissionId"] = "another-submission"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/comparisons",
            content=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
