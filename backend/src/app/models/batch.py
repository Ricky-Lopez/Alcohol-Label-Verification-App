from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field

from app.models.base import ContractModel, DurationMilliseconds, Identifier, ShortText
from app.models.label import ImageMediaType
from app.models.verification import OverallReviewStatus


class BatchStatus(StrEnum):
    PROCESSING = "processing"
    PAUSED = "paused"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"


class BatchItemStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    FAILED = "failed"
    SKIPPED = "skipped"


class BatchImageDeclaration(ContractModel):
    filename: Annotated[str, Field(min_length=1, max_length=255)]
    media_type: ImageMediaType
    size_bytes: Annotated[int, Field(gt=0, le=20_000_000)]


class BatchImageManifest(ContractModel):
    images: Annotated[list[BatchImageDeclaration], Field(min_length=1, max_length=200)]


class BatchValidationIssue(ContractModel):
    row: Annotated[int, Field(ge=1)] | None = None
    field: ShortText | None = None
    code: Identifier
    message: ShortText


class BatchValidationResponse(ContractModel):
    message: ShortText
    issues: Annotated[list[BatchValidationIssue], Field(min_length=1)]


class BatchItemSummary(ContractModel):
    batch_item_id: Identifier
    row_number: Annotated[int, Field(ge=2)]
    filename: Annotated[str, Field(min_length=1, max_length=255)]
    record_id: Identifier
    brand_name: ShortText
    status: BatchItemStatus
    overall_status: OverallReviewStatus | None = None
    queue_item_id: Identifier | None = None
    error_code: Identifier | None = None
    error_message: ShortText | None = None
    retryable: bool = False
    duration_ms: DurationMilliseconds | None = None


class BatchDetail(ContractModel):
    batch_id: Identifier
    status: BatchStatus
    total_count: Annotated[int, Field(ge=1, le=200)]
    processed_count: Annotated[int, Field(ge=0)]
    ready_count: Annotated[int, Field(ge=0)]
    failed_count: Annotated[int, Field(ge=0)]
    skipped_count: Annotated[int, Field(ge=0)]
    created_at: datetime
    completed_at: datetime | None = None
    session_scoped: bool = True
    items: list[BatchItemSummary]
