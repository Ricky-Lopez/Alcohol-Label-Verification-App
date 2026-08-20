import json
from io import BytesIO
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from pydantic import ValidationError

from app.api.extractions import get_ocr_extractor
from app.config import Settings, get_settings
from app.extraction.image_processing import PreparedImage
from app.extraction.providers import (
    ExtractorConfigurationError,
    ExtractorInvalidResponseError,
    ExtractorRateLimitError,
    ExtractorRefusedError,
    ExtractorTimeoutError,
    MockOcrExtractor,
    MockScenario,
    ProviderImageExtraction,
)
from app.main import app
from app.models.extraction import ExtractionIssueCode, ExtractionStatus
from app.models.label import ImageMediaType, LabelImageInput, VerificationSubmission

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SUBMISSION_FIXTURE_PATH = (
    REPOSITORY_ROOT / "fixtures" / "applications" / "example-distilled-spirits-submission.json"
)
MOCK_SCENARIOS_PATH = REPOSITORY_ROOT / "fixtures" / "extractions" / "mock-scenarios.json"
MOCK_SCENARIOS = json.loads(MOCK_SCENARIOS_PATH.read_text(encoding="utf-8"))


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 50), "white").save(output, format="PNG")
    return output.getvalue()


def submission_for(data: bytes, *, image_count: int = 1) -> VerificationSubmission:
    submission = VerificationSubmission.model_validate_json(
        SUBMISSION_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    images = [
        LabelImageInput(
            client_image_id=f"image-{index + 1}",
            file_name=f"label-{index + 1}.png",
            media_type=ImageMediaType.PNG,
            size_bytes=len(data),
        )
        for index in range(image_count)
    ]
    return submission.model_copy(update={"images": images})


async def post_extraction(
    *,
    scenario: str | None,
    image_count: int = 1,
) -> tuple[int, dict[str, object]]:
    data = png_bytes()
    submission = submission_for(data, image_count=image_count)
    files = [
        ("images", (image.file_name, data, image.media_type.value)) for image in submission.images
    ]
    headers = {"X-OCR-Mock-Scenario": scenario} if scenario else {}
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/extractions",
            data={"submission": submission.model_dump_json(by_alias=True)},
            files=files,
            headers=headers,
        )
    return response.status_code, response.json()


@pytest.fixture(autouse=True)
def mock_dependencies() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_environment="test",
        ocr_provider="mock",
    )
    app.dependency_overrides[get_ocr_extractor] = MockOcrExtractor
    yield
    app.dependency_overrides.clear()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "scenario_case",
    MOCK_SCENARIOS,
    ids=[scenario["scenario"] for scenario in MOCK_SCENARIOS],
)
async def test_mock_scenarios_return_typed_extraction_results(
    scenario_case: dict[str, object],
) -> None:
    status, body = await post_extraction(scenario=str(scenario_case["scenario"]))

    assert status == scenario_case["httpStatus"]
    assert body["status"] == scenario_case["extractionStatus"]
    issue_code = scenario_case["issueCode"]
    if issue_code is None:
        assert body["issues"] == []
    else:
        assert issue_code in {issue["code"] for issue in body["issues"]}


@pytest.mark.anyio
async def test_warning_text_remains_verbatim_and_unnormalized() -> None:
    _, body = await post_extraction(scenario="warning_mismatch")

    warning = next(
        candidate
        for candidate in body["fieldCandidates"]
        if candidate["field"] == "government_warning_text"
    )
    assert "may cause serious health problems" in warning["rawText"]
    assert warning["normalizedValue"] is None


@pytest.mark.anyio
async def test_upload_metadata_must_match_binary_file() -> None:
    data = png_bytes()
    submission = submission_for(data)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/extractions",
            data={"submission": submission.model_dump_json(by_alias=True)},
            files={"images": ("different.png", data, "image/png")},
            headers={"X-OCR-Mock-Scenario": "success"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == ("The uploaded image filename does not match its metadata.")


@pytest.mark.anyio
async def test_mock_header_is_rejected_for_openai_provider() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_environment="test",
        ocr_provider="openai",
    )

    status, body = await post_extraction(scenario="success")

    assert status == 422
    assert body["detail"] == "Mock OCR scenarios are available only with the mock provider."


class PartialTimeoutExtractor(MockOcrExtractor):
    async def extract_image(
        self,
        image: PreparedImage,
        *,
        scenario: MockScenario | None = None,
    ) -> ProviderImageExtraction:
        if image.client_image_id == "image-2":
            raise ExtractorTimeoutError
        return await super().extract_image(image, scenario=MockScenario.SUCCESS)


@pytest.mark.anyio
async def test_one_timed_out_image_preserves_other_image_results() -> None:
    app.dependency_overrides[get_ocr_extractor] = PartialTimeoutExtractor

    status, body = await post_extraction(scenario=None, image_count=2)

    assert status == 200
    assert body["status"] == ExtractionStatus.PARTIAL.value
    assert {segment["imageId"] for segment in body["segments"]} == {"image-1"}
    assert ExtractionIssueCode.EXTRACTOR_TIMEOUT.value in {
        issue["code"] for issue in body["issues"]
    }


class RaisingExtractor(MockOcrExtractor):
    error_type: type[RuntimeError] = RuntimeError

    async def extract_image(
        self,
        image: PreparedImage,
        *,
        scenario: MockScenario | None = None,
    ) -> ProviderImageExtraction:
        raise self.error_type


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error_type", "http_status", "issue_code"),
    [
        (ExtractorConfigurationError, 503, "extractor_unavailable"),
        (ExtractorRateLimitError, 503, "extractor_unavailable"),
        (ExtractorRefusedError, 502, "extractor_refused"),
        (ExtractorInvalidResponseError, 502, "extractor_invalid_response"),
    ],
)
async def test_provider_failures_return_typed_safe_results(
    error_type: type[RuntimeError],
    http_status: int,
    issue_code: str,
) -> None:
    class ScenarioExtractor(RaisingExtractor):
        pass

    ScenarioExtractor.error_type = error_type
    app.dependency_overrides[get_ocr_extractor] = ScenarioExtractor

    status, body = await post_extraction(scenario=None)

    assert status == http_status
    assert body["status"] == "failed"
    assert body["fieldCandidates"] == []
    assert body["issues"][0]["code"] == issue_code
    assert "OpenAI" not in body["issues"][0]["message"]


def test_mock_provider_cannot_run_in_production() -> None:
    with pytest.raises(ValidationError, match="cannot run in production"):
        Settings(app_environment="production", ocr_provider="mock")
