from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.models.base import (
    Confidence,
    ContractModel,
    DurationMilliseconds,
    Identifier,
    LabelText,
    ShortText,
)
from app.models.extraction import (
    BoundingPolygon,
    ExtractorReference,
    OcrExtractionResult,
    VerificationField,
)
from app.models.label import ApplicationRecord, LabelImageInput, VerificationSubmission


class VerificationOutcome(StrEnum):
    MATCH = "match"
    POSSIBLE_MATCH = "possible_match"
    MISMATCH = "mismatch"
    NOT_FOUND = "not_found"
    NOT_APPLICABLE = "not_applicable"
    UNABLE_TO_EVALUATE = "unable_to_evaluate"


class OverallReviewStatus(StrEnum):
    NO_DISCREPANCIES_FOUND = "no_discrepancies_found"
    REVIEW_NEEDED = "review_needed"
    ANALYSIS_INCOMPLETE = "analysis_incomplete"


class FindingSeverity(StrEnum):
    INFORMATION = "information"
    REVIEW = "review"
    DISCREPANCY = "discrepancy"


class RulesetReference(ContractModel):
    ruleset_id: Identifier
    version: ShortText
    effective_date: date
    source_uri: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None


class ComparisonValue(ContractModel):
    display_value: LabelText
    normalized_value: Annotated[str, Field(min_length=1, max_length=5_000)] | None = None
    unit: ShortText | None = None


class EvidenceReference(ContractModel):
    image_id: Identifier
    segment_ids: list[Identifier] = Field(default_factory=list)
    region: BoundingPolygon | None = None
    excerpt: LabelText | None = None


class ComparisonInput(ContractModel):
    comparison_id: Identifier
    application: ApplicationRecord
    images: Annotated[list[LabelImageInput], Field(min_length=1, max_length=12)]
    extraction: OcrExtractionResult
    ruleset: RulesetReference

    @model_validator(mode="after")
    def validate_related_records(self) -> "ComparisonInput":
        image_ids = {image.client_image_id for image in self.images}
        extraction_image_ids = {segment.image_id for segment in self.extraction.segments}
        if not extraction_image_ids.issubset(image_ids):
            raise ValueError("OCR segments reference images outside the comparison input")
        return self


class ComparisonRequest(ContractModel):
    """Public comparison request; the API selects the approved ruleset server-side."""

    comparison_id: Identifier
    submission: VerificationSubmission
    extraction: OcrExtractionResult

    @model_validator(mode="after")
    def validate_submission_correlation(self) -> "ComparisonRequest":
        if self.extraction.submission_id != self.submission.submission_id:
            raise ValueError("extraction submissionId must match the comparison submission")
        image_ids = {image.client_image_id for image in self.submission.images}
        segment_image_ids = {segment.image_id for segment in self.extraction.segments}
        if not segment_image_ids.issubset(image_ids):
            raise ValueError("OCR segments reference images outside the comparison submission")
        return self


class VerificationFinding(ContractModel):
    field: VerificationField
    outcome: VerificationOutcome
    severity: FindingSeverity
    rule_id: Identifier
    explanation: LabelText
    expected: ComparisonValue | None = None
    detected: list[ComparisonValue] = Field(default_factory=list)
    confidence: Confidence | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)


class VerificationResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    verification_id: Identifier
    submission_id: Identifier
    record_id: Identifier
    overall_status: OverallReviewStatus
    decision_support_only: Literal[True] = True
    ruleset: RulesetReference
    extractor: ExtractorReference
    findings: Annotated[list[VerificationFinding], Field(min_length=1)]
    started_at: datetime
    completed_at: datetime
    duration_ms: DurationMilliseconds

    @model_validator(mode="after")
    def validate_timing_and_summary(self) -> "VerificationResult":
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("verification timestamps must include a timezone")
        if self.completed_at < self.started_at:
            raise ValueError("completedAt must not precede startedAt")

        review_outcomes = {
            VerificationOutcome.POSSIBLE_MATCH,
            VerificationOutcome.MISMATCH,
            VerificationOutcome.NOT_FOUND,
            VerificationOutcome.UNABLE_TO_EVALUATE,
        }
        if self.overall_status == OverallReviewStatus.NO_DISCREPANCIES_FOUND and any(
            finding.outcome in review_outcomes for finding in self.findings
        ):
            raise ValueError("noDiscrepanciesFound cannot contain a review finding")

        return self
