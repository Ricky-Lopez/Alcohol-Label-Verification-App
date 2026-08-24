"""Canonical domain contracts shared by API and verification modules."""

from app.models.batch import BatchDetail
from app.models.contract import VerificationContract
from app.models.extraction import OcrExtractionResult
from app.models.label import ApplicationRecord, VerificationSubmission
from app.models.review_queue import (
    ReviewQueueCreateRequest,
    ReviewQueueItemDetail,
    ReviewQueueResponse,
)
from app.models.verification import ComparisonInput, ComparisonRequest, VerificationResult

__all__ = [
    "ApplicationRecord",
    "BatchDetail",
    "ComparisonInput",
    "ComparisonRequest",
    "OcrExtractionResult",
    "ReviewQueueItemDetail",
    "ReviewQueueCreateRequest",
    "ReviewQueueResponse",
    "VerificationContract",
    "VerificationResult",
    "VerificationSubmission",
]
