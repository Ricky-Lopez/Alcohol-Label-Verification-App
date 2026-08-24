import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.contract import VerificationContract
from app.models.extraction import (
    BoundingPolygon,
    ExtractedFieldCandidate,
    ExtractionStatus,
    ExtractionTiming,
    ExtractorReference,
    OcrExtractionResult,
    Point,
    TextSegment,
    VerificationField,
)
from app.models.label import (
    AlcoholContent,
    ApplicationRecord,
    BeverageType,
    CountryOfOrigin,
    ExpectedLabelFields,
    ImageMediaType,
    IntakeSource,
    LabelImageInput,
    NetContents,
    NetContentsUnit,
    PostalAddress,
    ResponsibleParty,
    VerificationSubmission,
)
from app.models.verification import (
    ComparisonValue,
    FindingSeverity,
    OverallReviewStatus,
    RulesetReference,
    VerificationFinding,
    VerificationOutcome,
    VerificationResult,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY_ROOT / "contracts" / "verification.schema.json"
SUBMISSION_FIXTURE_PATH = (
    REPOSITORY_ROOT / "fixtures" / "applications" / "example-distilled-spirits-submission.json"
)


def expected_label(*, country_of_origin: CountryOfOrigin | None = None) -> ExpectedLabelFields:
    return ExpectedLabelFields(
        brand_name="OLD TOM DISTILLERY",
        class_type_designation="Kentucky Straight Bourbon Whiskey",
        alcohol_content=AlcoholContent(
            abv_percent=45,
            proof=90,
            expected_display_text="45% Alc./Vol. (90 Proof)",
        ),
        net_contents=NetContents(
            value=750,
            unit=NetContentsUnit.MILLILITER,
            expected_display_text="750 mL",
        ),
        responsible_parties=[
            ResponsibleParty(
                name="Example Distilling Company",
                address=PostalAddress(
                    city="Frankfort",
                    region="KY",
                    country_code="US",
                ),
                statement_prefix="Distilled and bottled by",
            )
        ],
        country_of_origin=country_of_origin,
    )


def application_record(*, imported: bool = False) -> ApplicationRecord:
    return ApplicationRecord(
        record_id="app-001",
        intake_source=IntakeSource.PRELOADED,
        beverage_type=BeverageType.DISTILLED_SPIRITS,
        imported=imported,
        expected_label=expected_label(
            country_of_origin=(
                CountryOfOrigin(country_code="GB", display_name="United Kingdom")
                if imported
                else None
            )
        ),
    )


def image_input() -> LabelImageInput:
    return LabelImageInput(
        client_image_id="image-001",
        file_name="synthetic-bourbon-label.png",
        media_type=ImageMediaType.PNG,
        size_bytes=2048,
    )


def extraction_result() -> OcrExtractionResult:
    region = BoundingPolygon(
        points=[
            Point(x=0.1, y=0.1),
            Point(x=0.9, y=0.1),
            Point(x=0.9, y=0.2),
            Point(x=0.1, y=0.2),
        ]
    )
    segment = TextSegment(
        segment_id="segment-001",
        image_id="image-001",
        raw_text="OLD TOM DISTILLERY",
        confidence=0.98,
        region=region,
    )
    return OcrExtractionResult(
        extraction_id="extraction-001",
        submission_id="submission-001",
        status=ExtractionStatus.SUCCEEDED,
        extractor=ExtractorReference(name="synthetic-ocr", version="0.1.0"),
        duration_ms=100,
        timing=ExtractionTiming(image_preparation_ms=20, provider_ms=75),
        segments=[segment],
        field_candidates=[
            ExtractedFieldCandidate(
                field=VerificationField.BRAND_NAME,
                raw_text=segment.raw_text,
                normalized_value="old tom distillery",
                confidence=segment.confidence,
                evidence_segment_ids=[segment.segment_id],
            )
        ],
    )


def test_submission_serializes_with_camel_case_boundary_names() -> None:
    submission = VerificationSubmission(
        submission_id="submission-001",
        application=application_record(),
        images=[image_input()],
    )

    serialized = submission.model_dump(mode="json", by_alias=True)

    assert serialized["submissionId"] == "submission-001"
    assert serialized["application"]["expectedLabel"]["brandName"] == "OLD TOM DISTILLERY"
    assert serialized["images"][0]["mediaType"] == "image/png"


def test_synthetic_submission_fixture_matches_frontend_contract() -> None:
    submission = VerificationSubmission.model_validate_json(
        SUBMISSION_FIXTURE_PATH.read_text(encoding="utf-8")
    )

    assert submission.application.beverage_type == BeverageType.DISTILLED_SPIRITS
    assert submission.application.expected_label.alcohol_content is not None
    assert submission.application.expected_label.alcohol_content.abv_percent == 45


def test_imported_application_requires_country_of_origin() -> None:
    with pytest.raises(ValidationError, match="countryOfOrigin is required"):
        ApplicationRecord(
            record_id="app-002",
            intake_source=IntakeSource.AD_HOC,
            beverage_type=BeverageType.WINE,
            imported=True,
            expected_label=expected_label(),
        )


def test_distilled_spirits_require_alcohol_content() -> None:
    label = expected_label().model_copy(update={"alcohol_content": None})

    with pytest.raises(ValidationError, match="alcoholContent is required"):
        ApplicationRecord(
            record_id="app-003",
            intake_source=IntakeSource.AD_HOC,
            beverage_type=BeverageType.DISTILLED_SPIRITS,
            imported=False,
            expected_label=label,
        )


def test_ocr_candidates_must_reference_known_segments() -> None:
    extraction = extraction_result()
    bad_candidate = extraction.field_candidates[0].model_copy(
        update={"evidence_segment_ids": ["missing-segment"]}
    )

    with pytest.raises(ValidationError, match="unknown segment"):
        OcrExtractionResult(
            extraction_id=extraction.extraction_id,
            submission_id=extraction.submission_id,
            status=extraction.status,
            extractor=extraction.extractor,
            duration_ms=extraction.duration_ms,
            timing=extraction.timing,
            segments=extraction.segments,
            field_candidates=[bad_candidate],
        )


def test_openai_compatible_evidence_can_omit_confidence_and_region() -> None:
    segment = TextSegment(
        segment_id="segment-openai-001",
        image_id="image-001",
        raw_text="GOVERNMENT WARNING:",
    )
    candidate = ExtractedFieldCandidate(
        field=VerificationField.GOVERNMENT_WARNING_TEXT,
        raw_text=segment.raw_text,
        normalized_value=None,
        evidence_segment_ids=[segment.segment_id],
    )

    assert segment.confidence is None
    assert segment.region is None
    assert candidate.confidence is None


def test_no_discrepancies_summary_rejects_review_findings() -> None:
    ruleset = RulesetReference(
        ruleset_id="ttb-prototype",
        version="2026-08-19",
        effective_date=date(2026, 8, 19),
    )
    finding = VerificationFinding(
        field=VerificationField.BRAND_NAME,
        outcome=VerificationOutcome.MISMATCH,
        severity=FindingSeverity.DISCREPANCY,
        rule_id="brand-name-match",
        explanation="The detected brand does not match the application value.",
        expected=ComparisonValue(display_value="OLD TOM DISTILLERY"),
        detected=[ComparisonValue(display_value="OLD TIME DISTILLERY")],
        confidence=0.97,
    )

    with pytest.raises(ValidationError, match="cannot contain a review finding"):
        VerificationResult(
            verification_id="verification-001",
            submission_id="submission-001",
            record_id="app-001",
            overall_status=OverallReviewStatus.NO_DISCREPANCIES_FOUND,
            ruleset=ruleset,
            extractor=extraction_result().extractor,
            findings=[finding],
            started_at=datetime(2026, 8, 19, 12, 0, tzinfo=UTC),
            completed_at=datetime(2026, 8, 19, 12, 0, 1, tzinfo=UTC),
            duration_ms=1000,
        )


def test_committed_contract_matches_canonical_models() -> None:
    committed_schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    generated_schema = VerificationContract.model_json_schema(mode="serialization")
    generated_schema["$id"] = (
        "https://alcohol-label-verification.local/contracts/verification.schema.json"
    )
    generated_schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"

    assert committed_schema == generated_schema
