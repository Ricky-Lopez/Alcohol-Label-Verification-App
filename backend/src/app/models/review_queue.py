from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator

from app.models.base import ContractModel, Identifier, LabelText, ShortText
from app.models.label import ApplicationRecord, LabelPanelType
from app.models.verification import OverallReviewStatus, VerificationResult


class HumanReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewQueueImage(ContractModel):
    image_id: Identifier
    panel_type: LabelPanelType
    alt_text: ShortText
    image_url: Annotated[str, Field(min_length=1, max_length=2_000)]


class ReviewQueueItemSummary(ContractModel):
    queue_item_id: Identifier
    position: Annotated[int, Field(ge=1)]
    record_id: Identifier
    brand_name: ShortText
    beverage_type: ShortText
    overall_status: OverallReviewStatus
    attention_count: Annotated[int, Field(ge=0)]
    queued_at: datetime
    version: Annotated[int, Field(ge=1)]


class ReviewQueueItemDetail(ContractModel):
    summary: ReviewQueueItemSummary
    application: ApplicationRecord
    verification: VerificationResult
    images: list[ReviewQueueImage]


class ReviewQueueResponse(ContractModel):
    items: list[ReviewQueueItemSummary]
    total_count: Annotated[int, Field(ge=0)]
    session_scoped: bool = True


class HumanReviewDecisionRequest(ContractModel):
    decision: HumanReviewDecision
    comment: Annotated[str, Field(max_length=2_000)] | None = None

    @field_validator("comment")
    @classmethod
    def empty_comment_is_none(cls, value: str | None) -> str | None:
        return value or None


class HumanReviewReceipt(ContractModel):
    decision_id: Identifier
    queue_item_id: Identifier
    decision: HumanReviewDecision
    comment: LabelText | None = None
    decided_at: datetime
    undo_expires_at: datetime
    remaining_count: Annotated[int, Field(ge=0)]
