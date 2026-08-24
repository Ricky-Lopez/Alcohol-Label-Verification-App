from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, RateLimitError
from pydantic import ValidationError

from app.extraction.image_processing import PreparedImage
from app.extraction.providers import (
    OCR_INSTRUCTIONS,
    ExtractorInvalidResponseError,
    ExtractorRateLimitError,
    ExtractorRefusedError,
    ExtractorTimeoutError,
    ExtractorUnavailableError,
    ImageClassification,
    OcrObservationField,
    OpenAiOcrExtractor,
    ProviderImageExtraction,
    ProviderObservation,
)
from app.rules import GOVERNMENT_WARNING_TEXT


class FakeResponses:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.arguments: dict[str, Any] = {}

    async def parse(self, **kwargs: Any) -> object:
        self.arguments = kwargs
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def prepared_image() -> PreparedImage:
    return PreparedImage(
        client_image_id="image-001",
        source_file_name="label.png",
        media_type="image/png",
        data=b"synthetic-image-bytes",
        width=100,
        height=50,
    )


def completed_response(parsed: ProviderImageExtraction) -> SimpleNamespace:
    content = SimpleNamespace(type="output_text", parsed=parsed)
    message = SimpleNamespace(type="message", content=[content])
    return SimpleNamespace(status="completed", output=[message])


@pytest.mark.anyio
async def test_openai_adapter_uses_structured_stateless_image_request() -> None:
    parsed = ProviderImageExtraction(
        classification=ImageClassification.ALCOHOL_LABEL,
        observations=[
            ProviderObservation(
                field=OcrObservationField.GOVERNMENT_WARNING_TEXT,
                raw_text="GOVERNMENT WARNING:",
                normalized_value=None,
                uncertain=False,
            )
        ],
        warning_text_incomplete=False,
    )
    responses = FakeResponses(response=completed_response(parsed))
    extractor = OpenAiOcrExtractor(
        api_key="test-key",
        model="gpt-4o-mini",
        image_detail="high",
        timeout_seconds=4,
        client=FakeClient(responses),  # type: ignore[arg-type]
    )

    result = await extractor.extract_image(prepared_image())

    assert result == parsed
    assert responses.arguments["text_format"] is ProviderImageExtraction
    assert responses.arguments["store"] is False
    assert responses.arguments["max_output_tokens"] == 2_000
    image_input = responses.arguments["input"][0]["content"][1]
    assert image_input["detail"] == "high"
    assert image_input["image_url"].startswith("data:image/png;base64,")
    assert "Never infer, correct, complete, compare, paraphrase" in OCR_INSTRUCTIONS
    assert "complete visible brand-name lockup" in OCR_INSTRUCTIONS
    assert "Never drop a word merely because it also looks like a" in OCR_INSTRUCTIONS
    assert "product descriptor or business term" in OCR_INSTRUCTIONS
    for field in (
        "brand_name",
        "class_type_designation",
        "alcohol_content",
        "net_contents",
        "responsible_party_name",
        "responsible_party_address",
        "country_of_origin",
        "government_warning_text",
        "government_warning_heading_case",
        "government_warning_heading_weight",
    ):
        assert field in OCR_INSTRUCTIONS
    assert "expectedLabel" not in str(responses.arguments)
    assert "OLD TOM DISTILLERY" not in str(responses.arguments)
    assert GOVERNMENT_WARNING_TEXT not in str(responses.arguments)
    field_schema = ProviderImageExtraction.model_json_schema()["$defs"]["OcrObservationField"]
    assert set(field_schema["enum"]) == {
        "brand_name",
        "class_type_designation",
        "alcohol_content",
        "net_contents",
        "responsible_party_name",
        "responsible_party_address",
        "country_of_origin",
        "government_warning_text",
        "government_warning_heading_case",
        "government_warning_heading_weight",
    }


def test_provider_observations_allow_missing_uncertain_and_duplicate_fields() -> None:
    observations = [
        ProviderObservation(
            field=OcrObservationField.BRAND_NAME,
            raw_text="FIRST BRAND",
            normalized_value=None,
            uncertain=False,
        ),
        ProviderObservation(
            field=OcrObservationField.BRAND_NAME,
            raw_text="SECOND BRAND",
            normalized_value=None,
            uncertain=True,
        ),
        ProviderObservation(
            field=OcrObservationField.GOVERNMENT_WARNING_HEADING_WEIGHT,
            raw_text="GOVERNMENT WARNING:",
            normalized_value=None,
            uncertain=True,
        ),
    ]

    result = ProviderImageExtraction(
        classification=ImageClassification.UNCERTAIN,
        observations=observations,
        warning_text_incomplete=False,
    )

    assert result.observations == observations


@pytest.mark.parametrize(
    ("field", "normalized_value"),
    [
        (OcrObservationField.BRAND_NAME.value, "normalized brand"),
        (OcrObservationField.GOVERNMENT_WARNING_TEXT.value, "normalized warning"),
        (OcrObservationField.GOVERNMENT_WARNING_HEADING_CASE.value, "mixed_case"),
        ("appellation_of_origin", None),
    ],
)
def test_provider_observations_reject_out_of_scope_or_malformed_values(
    field: str,
    normalized_value: str | None,
) -> None:
    with pytest.raises(ValidationError):
        ProviderObservation(
            field=field,
            raw_text="visible text",
            normalized_value=normalized_value,
            uncertain=False,
        )


@pytest.mark.anyio
async def test_openai_adapter_maps_timeout() -> None:
    timeout = APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    extractor = OpenAiOcrExtractor(
        api_key="test-key",
        model="gpt-4o-mini",
        image_detail="high",
        timeout_seconds=4,
        client=FakeClient(FakeResponses(error=timeout)),  # type: ignore[arg-type]
    )

    with pytest.raises(ExtractorTimeoutError):
        await extractor.extract_image(prepared_image())


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_error", "expected_error"),
    [
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://api.openai.com/v1/responses")
            ),
            ExtractorUnavailableError,
        ),
        (
            RateLimitError(
                "rate limited",
                response=httpx.Response(
                    429,
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                body=None,
            ),
            ExtractorRateLimitError,
        ),
    ],
)
async def test_openai_adapter_maps_connection_and_rate_limit_errors(
    provider_error: Exception,
    expected_error: type[Exception],
) -> None:
    extractor = OpenAiOcrExtractor(
        api_key="test-key",
        model="gpt-4o-mini",
        image_detail="high",
        timeout_seconds=4,
        client=FakeClient(FakeResponses(error=provider_error)),  # type: ignore[arg-type]
    )

    with pytest.raises(expected_error):
        await extractor.extract_image(prepared_image())


@pytest.mark.anyio
async def test_openai_adapter_detects_refusal_and_incomplete_response() -> None:
    refusal = SimpleNamespace(
        status="completed",
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="refusal", refusal="cannot process")],
            )
        ],
    )
    extractor = OpenAiOcrExtractor(
        api_key="test-key",
        model="gpt-4o-mini",
        image_detail="high",
        timeout_seconds=4,
        client=FakeClient(FakeResponses(response=refusal)),  # type: ignore[arg-type]
    )
    with pytest.raises(ExtractorRefusedError):
        await extractor.extract_image(prepared_image())

    incomplete = SimpleNamespace(status="incomplete", output=[])
    extractor = OpenAiOcrExtractor(
        api_key="test-key",
        model="gpt-4o-mini",
        image_detail="high",
        timeout_seconds=4,
        client=FakeClient(FakeResponses(response=incomplete)),  # type: ignore[arg-type]
    )
    with pytest.raises(ExtractorInvalidResponseError):
        await extractor.extract_image(prepared_image())
