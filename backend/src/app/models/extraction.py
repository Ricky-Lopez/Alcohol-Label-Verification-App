from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from app.models.base import (
    Confidence,
    ContractModel,
    DurationMilliseconds,
    Identifier,
    LabelText,
    NormalizedCoordinate,
    ShortText,
)


class VerificationField(StrEnum):
    BRAND_NAME = "brand_name"
    CLASS_TYPE_DESIGNATION = "class_type_designation"
    ALCOHOL_CONTENT = "alcohol_content"
    NET_CONTENTS = "net_contents"
    RESPONSIBLE_PARTY_NAME = "responsible_party_name"
    RESPONSIBLE_PARTY_ADDRESS = "responsible_party_address"
    COUNTRY_OF_ORIGIN = "country_of_origin"
    APPELLATION_OF_ORIGIN = "appellation_of_origin"
    GOVERNMENT_WARNING_TEXT = "government_warning_text"
    GOVERNMENT_WARNING_HEADING_CASE = "government_warning_heading_case"
    GOVERNMENT_WARNING_HEADING_WEIGHT = "government_warning_heading_weight"
    GOVERNMENT_WARNING_PROMINENCE = "government_warning_prominence"
    GOVERNMENT_WARNING_PLACEMENT = "government_warning_placement"
    GOVERNMENT_WARNING_TYPE_SIZE = "government_warning_type_size"
    SAME_FIELD_OF_VISION = "same_field_of_vision"
    GENERAL_LEGIBILITY = "general_legibility"
    ADDITIONAL_REQUIRED_STATEMENT = "additional_required_statement"


class ExtractionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class ExtractionIssueCode(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    NO_TEXT_FOUND = "no_text_found"
    IMAGE_UNREADABLE = "image_unreadable"
    UNSUPPORTED_LAYOUT = "unsupported_layout"
    EXTRACTOR_TIMEOUT = "extractor_timeout"
    EXTRACTOR_UNAVAILABLE = "extractor_unavailable"


class Point(ContractModel):
    x: NormalizedCoordinate
    y: NormalizedCoordinate


class BoundingPolygon(ContractModel):
    points: Annotated[list[Point], Field(min_length=3, max_length=8)]


class TextSegment(ContractModel):
    segment_id: Identifier
    image_id: Identifier
    raw_text: LabelText
    confidence: Confidence
    region: BoundingPolygon
    orientation_degrees: Annotated[float, Field(ge=-180, le=180)] | None = None


class ExtractedFieldCandidate(ContractModel):
    field: VerificationField
    raw_text: LabelText
    normalized_value: Annotated[str, Field(min_length=1, max_length=5_000)] | None = None
    confidence: Confidence
    evidence_segment_ids: Annotated[list[Identifier], Field(min_length=1)]


class ExtractionIssue(ContractModel):
    code: ExtractionIssueCode
    message: ShortText
    image_id: Identifier | None = None


class ExtractorReference(ContractModel):
    name: ShortText
    version: ShortText
    model_version: ShortText | None = None


class OcrExtractionResult(ContractModel):
    extraction_id: Identifier
    submission_id: Identifier
    status: ExtractionStatus
    extractor: ExtractorReference
    duration_ms: DurationMilliseconds
    segments: list[TextSegment] = Field(default_factory=list)
    field_candidates: list[ExtractedFieldCandidate] = Field(default_factory=list)
    issues: list[ExtractionIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_references(self) -> "OcrExtractionResult":
        segment_ids = {segment.segment_id for segment in self.segments}
        referenced_ids = {
            segment_id
            for candidate in self.field_candidates
            for segment_id in candidate.evidence_segment_ids
        }
        missing_ids = referenced_ids - segment_ids
        if missing_ids:
            raise ValueError("field candidate evidence references an unknown segment")

        if self.status == ExtractionStatus.FAILED and self.field_candidates:
            raise ValueError("a failed extraction cannot contain field candidates")

        return self
