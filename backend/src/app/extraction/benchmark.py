import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Protocol

from app.config import Settings
from app.extraction.image_processing import InvalidImageError, PreparedImage, prepare_image
from app.extraction.providers import (
    ExtractorConfigurationError,
    ExtractorError,
    ExtractorInvalidResponseError,
    ExtractorRateLimitError,
    ExtractorRefusedError,
    ExtractorTimeoutError,
    ExtractorUnavailableError,
    OcrExtractor,
    OpenAiOcrExtractor,
)
from app.models.label import ImageMediaType, LabelImageInput


class BenchmarkError(RuntimeError):
    """Safe error raised for invalid benchmark configuration or input."""


class Clock(Protocol):
    def __call__(self) -> float: ...


@dataclass(frozen=True, slots=True)
class BenchmarkSample:
    original_bytes: int
    processed_bytes: int
    width: int
    height: int
    image_preparation_ms: float
    provider_ms: float
    total_ms: float


def provider_failure_category(error: ExtractorError) -> str:
    """Return a safe diagnostic category without provider response content."""
    if isinstance(error, ExtractorTimeoutError):
        return "timeout"
    if isinstance(error, ExtractorRateLimitError):
        return "rate_limit"
    if isinstance(error, ExtractorUnavailableError):
        return "unavailable"
    if isinstance(error, ExtractorRefusedError):
        return "refusal"
    if isinstance(error, ExtractorInvalidResponseError):
        return "invalid_structured_response"
    if isinstance(error, ExtractorConfigurationError):
        return "configuration"
    return "provider_error"


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _media_type_for(path: Path) -> ImageMediaType:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return ImageMediaType.JPEG
    if suffix == ".png":
        return ImageMediaType.PNG
    raise BenchmarkError("Benchmark images must use a .jpg, .jpeg, or .png extension.")


def _prepare(path: Path, data: bytes, *, clock: Clock) -> tuple[PreparedImage, float]:
    media_type = _media_type_for(path)
    metadata = LabelImageInput(
        client_image_id="benchmark-image",
        file_name=path.name,
        media_type=media_type,
        size_bytes=len(data),
    )
    started = clock()
    prepared = prepare_image(
        metadata,
        upload_file_name=path.name,
        upload_media_type=media_type.value,
        data=data,
    )
    return prepared, (clock() - started) * 1000


async def run_benchmark(
    *,
    image_path: Path,
    runs: int,
    settings: Settings,
    extractor: OcrExtractor | None = None,
    clock: Clock = perf_counter,
) -> list[BenchmarkSample]:
    if runs < 1:
        raise BenchmarkError("Benchmark runs must be at least 1.")
    if settings.ocr_provider != "openai":
        raise BenchmarkError("The live benchmark requires OCR_PROVIDER=openai.")
    if settings.openai_api_key is None and extractor is None:
        raise BenchmarkError("The live benchmark requires OPENAI_API_KEY.")

    try:
        data = image_path.read_bytes()
    except OSError as error:
        raise BenchmarkError("The benchmark image could not be read.") from error

    active_extractor = extractor
    if active_extractor is None:
        active_extractor = OpenAiOcrExtractor(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_ocr_model,
            image_detail=settings.openai_image_detail,
            timeout_seconds=settings.openai_ocr_timeout_seconds,
        )

    samples: list[BenchmarkSample] = []
    for _ in range(runs):
        total_started = clock()
        prepared, preparation_ms = _prepare(image_path, data, clock=clock)
        provider_started = clock()
        await active_extractor.extract_image(prepared)
        provider_ms = (clock() - provider_started) * 1000
        samples.append(
            BenchmarkSample(
                original_bytes=len(data),
                processed_bytes=len(prepared.data),
                width=prepared.width,
                height=prepared.height,
                image_preparation_ms=preparation_ms,
                provider_ms=provider_ms,
                total_ms=(clock() - total_started) * 1000,
            )
        )
    return samples


def format_report(samples: Sequence[BenchmarkSample]) -> str:
    first = samples[0]
    ratio = first.processed_bytes / first.original_bytes

    def summary(name: str, values: Sequence[float]) -> str:
        return (
            f"{name}: min={min(values):.1f} ms, median={median(values):.1f} ms, "
            f"max={max(values):.1f} ms"
        )

    lines = [
        f"Runs: {len(samples)}",
        f"Original bytes: {first.original_bytes}",
        f"Processed bytes: {first.processed_bytes}",
        f"Compression ratio: {ratio:.3f}",
        f"Processed dimensions: {first.width}x{first.height}",
        summary("Image preparation", [sample.image_preparation_ms for sample in samples]),
        summary("Provider", [sample.provider_ms for sample in samples]),
        summary("Total", [sample.total_ms for sample in samples]),
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark live OpenAI OCR using only a synthetic or public alcohol-label image."
        )
    )
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--runs", default=1, type=_positive_integer)
    return parser


async def _main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        samples = await run_benchmark(
            image_path=args.image,
            runs=args.runs,
            settings=Settings(),
        )
    except (BenchmarkError, InvalidImageError) as error:
        print(f"Benchmark error: {error}")
        return 2
    except ExtractorError as error:
        category = provider_failure_category(error)
        print(
            f"Benchmark error ({category}): The live OCR provider could not complete the request."
        )
        return 2
    print(format_report(samples))
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
