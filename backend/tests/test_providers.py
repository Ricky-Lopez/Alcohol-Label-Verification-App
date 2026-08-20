from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APITimeoutError

from app.extraction.image_processing import PreparedImage
from app.extraction.providers import (
    OCR_INSTRUCTIONS,
    ExtractorInvalidResponseError,
    ExtractorRefusedError,
    ExtractorTimeoutError,
    ImageClassification,
    OpenAiOcrExtractor,
    ProviderImageExtraction,
    ProviderTextSegment,
)


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
        segments=[ProviderTextSegment(raw_text="GOVERNMENT WARNING:")],
        field_candidates=[],
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
    assert responses.arguments["max_output_tokens"] == 4_000
    image_input = responses.arguments["input"][0]["content"][1]
    assert image_input["detail"] == "high"
    assert image_input["image_url"].startswith("data:image/png;base64,")
    assert "Never infer, correct, complete, paraphrase" in OCR_INSTRUCTIONS
    assert "expectedLabel" not in str(responses.arguments)
    assert "OLD TOM DISTILLERY" not in str(responses.arguments)


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
