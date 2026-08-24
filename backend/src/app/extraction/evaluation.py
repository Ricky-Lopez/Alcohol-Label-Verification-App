"""Opt-in live OCR and comparison evaluation for the synthetic corpus."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from time import perf_counter

from app.comparison import compare
from app.config import Settings
from app.extraction.benchmark import BenchmarkError, _media_type_for, provider_failure_category
from app.extraction.image_processing import InvalidImageError, prepare_image
from app.extraction.providers import ExtractorError, OcrExtractor, OpenAiOcrExtractor
from app.extraction.service import run_extraction
from app.models.label import (
    AlcoholContent,
    ApplicationRecord,
    BeverageType,
    ImageMediaType,
    IntakeSource,
    LabelImageInput,
    LabelPanelType,
    NetContents,
    NetContentsUnit,
    PostalAddress,
    ResponsibleParty,
)
from app.models.verification import ComparisonInput, OverallReviewStatus, RulesetReference
from app.rules import (
    PROTOTYPE_RULESET_EFFECTIVE_DATE,
    PROTOTYPE_RULESET_ID,
    PROTOTYPE_RULESET_VERSION,
)


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    image: str
    expected_outcome: OverallReviewStatus
    brand_name: str
    class_type_designation: str
    abv_percent: float
    proof: float
    business_name: str
    city: str


@dataclass(frozen=True, slots=True)
class EvaluationSample:
    case_id: str
    expected_outcome: OverallReviewStatus
    actual_outcome: OverallReviewStatus
    extraction_status: str
    extraction_ms: int
    image_preparation_ms: int
    provider_ms: int
    comparison_ms: int
    outcome_matches_expectation: bool


def load_corpus(fixture_dir: Path) -> list[EvaluationCase]:
    try:
        manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkError("The OCR evaluation manifest could not be read.") from error
    try:
        cases = [
            EvaluationCase(
                case_id=item["id"],
                image=item["image"],
                expected_outcome=OverallReviewStatus(item["expectedOutcome"]),
                brand_name=item["brandName"],
                class_type_designation=item["classTypeDesignation"],
                abv_percent=float(item["abvPercent"]),
                proof=float(item["proof"]),
                business_name=item["businessName"],
                city=item["city"],
            )
            for item in manifest["cases"]
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise BenchmarkError("The OCR evaluation manifest is invalid.") from error
    if not cases or any(not (fixture_dir / case.image).is_file() for case in cases):
        raise BenchmarkError("The OCR evaluation corpus is incomplete.")
    return cases


def _application(case: EvaluationCase) -> ApplicationRecord:
    return ApplicationRecord(
        record_id=f"evaluation-record-{case.case_id}",
        intake_source=IntakeSource.PRELOADED,
        beverage_type=BeverageType.DISTILLED_SPIRITS,
        imported=False,
        expected_label={
            "brand_name": case.brand_name,
            "class_type_designation": case.class_type_designation,
            "alcohol_content": AlcoholContent(abv_percent=case.abv_percent, proof=case.proof),
            "net_contents": NetContents(value=750, unit=NetContentsUnit.MILLILITER),
            "responsible_parties": [
                ResponsibleParty(
                    name=case.business_name,
                    address=PostalAddress(city=case.city, region="KY", country_code="US"),
                )
            ],
        },
    )


def _ruleset() -> RulesetReference:
    return RulesetReference(
        ruleset_id=PROTOTYPE_RULESET_ID,
        version=PROTOTYPE_RULESET_VERSION,
        effective_date=PROTOTYPE_RULESET_EFFECTIVE_DATE,
        source_uri="docs/REQUIREMENTS.md#fr-016",
    )


async def evaluate_corpus(
    *,
    fixture_dir: Path,
    settings: Settings,
    extractor: OcrExtractor | None = None,
) -> list[EvaluationSample]:
    if settings.ocr_provider != "openai":
        raise BenchmarkError("The live evaluation requires OCR_PROVIDER=openai.")
    if settings.openai_api_key is None and extractor is None:
        raise BenchmarkError("The live evaluation requires OPENAI_API_KEY.")
    active_extractor = extractor or OpenAiOcrExtractor(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_ocr_model,
        image_detail=settings.openai_image_detail,
        timeout_seconds=settings.openai_ocr_timeout_seconds,
    )
    samples: list[EvaluationSample] = []
    for case in load_corpus(fixture_dir):
        path = fixture_dir / case.image
        data = path.read_bytes()
        media_type = _media_type_for(path)
        image = LabelImageInput(
            client_image_id=f"evaluation-image-{case.case_id}",
            file_name=path.name,
            media_type=ImageMediaType(media_type.value),
            size_bytes=len(data),
            panel_type=LabelPanelType.BRAND,
        )
        preparation_started = perf_counter()
        prepared = prepare_image(
            image,
            upload_file_name=path.name,
            upload_media_type=media_type.value,
            data=data,
        )
        preparation_ms = round((perf_counter() - preparation_started) * 1000)
        extraction = await run_extraction(
            extractor=active_extractor,
            submission_id=f"evaluation-submission-{case.case_id}",
            images=[prepared],
            image_preparation_ms=preparation_ms,
        )
        comparison_started = perf_counter()
        verification = compare(
            ComparisonInput(
                comparison_id=f"evaluation-comparison-{case.case_id}",
                application=_application(case),
                images=[image],
                extraction=extraction.result,
                ruleset=_ruleset(),
            )
        )
        comparison_ms = round((perf_counter() - comparison_started) * 1000)
        samples.append(
            EvaluationSample(
                case_id=case.case_id,
                expected_outcome=case.expected_outcome,
                actual_outcome=verification.overall_status,
                extraction_status=extraction.result.status.value,
                extraction_ms=extraction.result.duration_ms,
                image_preparation_ms=preparation_ms,
                provider_ms=extraction.result.timing.provider_ms,
                comparison_ms=comparison_ms,
                outcome_matches_expectation=verification.overall_status == case.expected_outcome,
            )
        )
    return samples


def format_evaluation_report(samples: Sequence[EvaluationSample]) -> str:
    if not samples:
        return "No evaluation samples."
    matches = sum(sample.outcome_matches_expectation for sample in samples)
    provider_ms = [sample.provider_ms for sample in samples]
    extraction_ms = [sample.extraction_ms for sample in samples]
    lines = [
        f"Cases: {len(samples)}",
        f"Outcome agreement: {matches}/{len(samples)}",
        (
            f"Provider ms: min={min(provider_ms)}, median={median(provider_ms):.1f}, "
            f"mean={mean(provider_ms):.1f}, max={max(provider_ms)}"
        ),
        (
            f"Extraction ms: min={min(extraction_ms)}, median={median(extraction_ms):.1f}, "
            f"mean={mean(extraction_ms):.1f}, max={max(extraction_ms)}"
        ),
    ]
    lines.extend(
        " | ".join(
            [
                sample.case_id,
                f"expected={sample.expected_outcome.value}",
                f"actual={sample.actual_outcome.value}",
                f"extraction={sample.extraction_status}",
                f"providerMs={sample.provider_ms}",
                f"comparisonMs={sample.comparison_ms}",
            ]
        )
        for sample in samples
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run live OCR evaluation on synthetic labels.")
    parser.add_argument("--fixture-dir", required=True, type=Path)
    return parser


async def _main(arguments: Sequence[str] | None = None) -> int:
    fixture_dir = build_parser().parse_args(arguments).fixture_dir
    try:
        samples = await evaluate_corpus(fixture_dir=fixture_dir, settings=Settings())
    except (BenchmarkError, InvalidImageError) as error:
        print(f"Evaluation error: {error}")
        return 2
    except ExtractorError as error:
        print(
            f"Evaluation error ({provider_failure_category(error)}): provider could not complete."
        )
        return 2
    print(format_evaluation_report(samples))
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
