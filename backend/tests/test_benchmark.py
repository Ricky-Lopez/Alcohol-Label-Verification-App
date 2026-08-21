from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.config import Settings
from app.extraction.benchmark import (
    BenchmarkError,
    format_report,
    provider_failure_category,
    run_benchmark,
)
from app.extraction.image_processing import PreparedImage
from app.extraction.providers import (
    ExtractorConfigurationError,
    ExtractorError,
    ExtractorInvalidResponseError,
    ExtractorRateLimitError,
    ExtractorRefusedError,
    ExtractorTimeoutError,
    ExtractorUnavailableError,
    ImageClassification,
    MockScenario,
    OcrObservationField,
    ProviderImageExtraction,
    ProviderObservation,
)
from app.models.extraction import ExtractorReference


class FakeExtractor:
    reference = ExtractorReference(name="fake", version="1")

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
                    field=OcrObservationField.BRAND_NAME,
                    raw_text="SECRET SYNTHETIC LABEL TEXT",
                    normalized_value=None,
                    uncertain=False,
                )
            ],
            warning_text_incomplete=False,
        )


def write_png(path: Path) -> None:
    output = BytesIO()
    Image.new("RGB", (100, 50), "white").save(output, format="PNG")
    path.write_bytes(output.getvalue())


def test_default_provider_timeout_is_thirty_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_OCR_TIMEOUT_SECONDS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.openai_ocr_timeout_seconds == 30


@pytest.mark.parametrize(
    ("error", "expected_category"),
    [
        (ExtractorTimeoutError(), "timeout"),
        (ExtractorRateLimitError(), "rate_limit"),
        (ExtractorUnavailableError(), "unavailable"),
        (ExtractorRefusedError(), "refusal"),
        (ExtractorInvalidResponseError(), "invalid_structured_response"),
        (ExtractorConfigurationError(), "configuration"),
        (ExtractorError(), "provider_error"),
    ],
)
def test_benchmark_reports_safe_provider_failure_categories(
    error: ExtractorError,
    expected_category: str,
) -> None:
    assert provider_failure_category(error) == expected_category


@pytest.mark.anyio
async def test_benchmark_reports_safe_compression_and_timing_metrics(tmp_path: Path) -> None:
    image_path = tmp_path / "synthetic-label.png"
    write_png(image_path)
    settings = Settings(
        app_environment="test",
        ocr_provider="openai",
        openai_api_key=None,
        _env_file=None,
    )

    samples = await run_benchmark(
        image_path=image_path,
        runs=2,
        settings=settings,
        extractor=FakeExtractor(),
    )
    report = format_report(samples)

    assert "Runs: 2" in report
    assert "Compression ratio:" in report
    assert "Processed dimensions: 100x50" in report
    assert "Provider:" in report
    assert "SECRET SYNTHETIC LABEL TEXT" not in report


@pytest.mark.anyio
async def test_benchmark_requires_live_provider_and_key(tmp_path: Path) -> None:
    image_path = tmp_path / "synthetic-label.png"
    write_png(image_path)

    with pytest.raises(BenchmarkError, match="OCR_PROVIDER=openai"):
        await run_benchmark(
            image_path=image_path,
            runs=1,
            settings=Settings(ocr_provider="mock", _env_file=None),
        )

    with pytest.raises(BenchmarkError, match="OPENAI_API_KEY"):
        await run_benchmark(
            image_path=image_path,
            runs=1,
            settings=Settings(ocr_provider="openai", openai_api_key=None, _env_file=None),
        )
