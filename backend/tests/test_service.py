import pytest

from app.extraction.image_processing import PreparedImage
from app.extraction.providers import (
    ExtractorTimeoutError,
    ImageClassification,
    MockOcrExtractor,
    MockScenario,
    OcrObservationField,
    ProviderImageExtraction,
    ProviderObservation,
)
from app.extraction.service import run_extraction


class SequenceClock:
    def __init__(self, values: list[float]) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


def prepared_image() -> PreparedImage:
    return PreparedImage(
        client_image_id="image-1",
        source_file_name="label.png",
        media_type="image/png",
        data=b"synthetic",
        width=100,
        height=50,
    )


class TimeoutExtractor(MockOcrExtractor):
    async def extract_image(
        self,
        image: PreparedImage,
        *,
        scenario: MockScenario | None = None,
    ) -> ProviderImageExtraction:
        raise ExtractorTimeoutError


class UncertainExtractor(MockOcrExtractor):
    async def extract_image(
        self,
        image: PreparedImage,
        *,
        scenario: MockScenario | None = None,
    ) -> ProviderImageExtraction:
        return await super().extract_image(image, scenario=MockScenario.UNCERTAIN_LABEL)


class WhitespaceWarningExtractor(MockOcrExtractor):
    async def extract_image(
        self,
        image: PreparedImage,
        *,
        scenario: MockScenario | None = None,
    ) -> ProviderImageExtraction:
        return ProviderImageExtraction(
            classification=ImageClassification.ALCOHOL_LABEL,
            observations=[
                ProviderObservation(
                    field=OcrObservationField.GOVERNMENT_WARNING_TEXT,
                    raw_text="  GOVERNMENT WARNING:\nVisible warning text.  ",
                    normalized_value=None,
                    uncertain=False,
                )
            ],
            warning_text_incomplete=False,
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("extractor", "expected_status"),
    [
        (MockOcrExtractor(), "succeeded"),
        (UncertainExtractor(), "partial"),
        (TimeoutExtractor(), "failed"),
    ],
)
async def test_service_reports_controlled_timing_for_success_and_failure(
    extractor: MockOcrExtractor,
    expected_status: str,
) -> None:
    clock = SequenceClock([10.0, 11.0, 13.0, 14.0])

    response = await run_extraction(
        extractor=extractor,
        submission_id="submission-1",
        images=[prepared_image()],
        image_preparation_ms=25,
        clock=clock,
    )

    assert response.result.status == expected_status
    assert response.result.duration_ms == 4_000
    assert response.result.timing.image_preparation_ms == 25
    assert response.result.timing.provider_ms == 2_000


@pytest.mark.anyio
async def test_service_preserves_warning_whitespace_verbatim() -> None:
    response = await run_extraction(
        extractor=WhitespaceWarningExtractor(),
        submission_id="submission-1",
        images=[prepared_image()],
    )

    expected = "  GOVERNMENT WARNING:\nVisible warning text.  "
    assert response.result.segments[0].raw_text == expected
    assert response.result.field_candidates[0].raw_text == expected
    assert response.result.field_candidates[0].normalized_value is None
