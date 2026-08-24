from pathlib import Path

import pytest

from app.config import Settings
from app.extraction.evaluation import (
    EvaluationSample,
    evaluate_corpus,
    format_evaluation_report,
    load_corpus,
)
from app.extraction.image_processing import PreparedImage
from app.extraction.providers import (
    ImageClassification,
    MockScenario,
    OcrObservationField,
    ProviderImageExtraction,
    ProviderObservation,
)
from app.models.extraction import ExtractorReference
from app.models.verification import OverallReviewStatus

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIRECTORY = REPOSITORY_ROOT / "fixtures" / "ocr_evaluation"


class FakeExtractor:
    reference = ExtractorReference(name="fake", version="1")

    async def extract_image(
        self, image: PreparedImage, *, scenario: MockScenario | None = None
    ) -> ProviderImageExtraction:
        return ProviderImageExtraction(
            classification=ImageClassification.ALCOHOL_LABEL,
            observations=[
                ProviderObservation(
                    field=OcrObservationField.BRAND_NAME,
                    raw_text="SYNTHETIC BRAND",
                    normalized_value=None,
                    uncertain=False,
                )
            ],
            warning_text_incomplete=False,
        )


def test_evaluation_corpus_has_controlled_cases() -> None:
    cases = load_corpus(FIXTURE_DIRECTORY)

    assert [case.case_id for case in cases] == [
        "clear-old-tom",
        "clear-meadowlark",
        "brand-mismatch",
        "abv-mismatch",
        "warning-incomplete",
        "warning-ambiguous",
    ]
    assert (
        sum(case.expected_outcome == OverallReviewStatus.NO_DISCREPANCIES_FOUND for case in cases)
        == 2
    )
    assert sum(case.expected_outcome == OverallReviewStatus.REVIEW_NEEDED for case in cases) == 2
    assert (
        sum(case.expected_outcome == OverallReviewStatus.ANALYSIS_INCOMPLETE for case in cases) == 2
    )


def test_evaluation_report_omits_label_content() -> None:
    report = format_evaluation_report(
        [
            EvaluationSample(
                case_id="clear-old-tom",
                expected_outcome=OverallReviewStatus.NO_DISCREPANCIES_FOUND,
                actual_outcome=OverallReviewStatus.NO_DISCREPANCIES_FOUND,
                extraction_status="succeeded",
                extraction_ms=700,
                image_preparation_ms=100,
                provider_ms=600,
                comparison_ms=1,
                outcome_matches_expectation=True,
            )
        ]
    )

    assert "Outcome agreement: 1/1" in report
    assert "Provider ms: min=600" in report
    assert "GOVERNMENT WARNING" not in report


@pytest.mark.anyio
async def test_evaluation_runs_against_the_full_corpus_with_an_injected_extractor() -> None:
    samples = await evaluate_corpus(
        fixture_dir=FIXTURE_DIRECTORY,
        settings=Settings(ocr_provider="openai", openai_api_key=None, _env_file=None),
        extractor=FakeExtractor(),
    )

    assert len(samples) == 6
    assert all(sample.extraction_status == "succeeded" for sample in samples)
