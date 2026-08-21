"""Canonical domain contracts shared by API and verification modules."""

from app.models.contract import VerificationContract
from app.models.extraction import OcrExtractionResult
from app.models.label import ApplicationRecord, VerificationSubmission
from app.models.review_queue import ReviewQueueItemDetail, ReviewQueueResponse
from app.models.verification import ComparisonInput, ComparisonRequest, VerificationResult

__all__ = [
    "ApplicationRecord",
    "ComparisonInput",
    "ComparisonRequest",
    "OcrExtractionResult",
    "ReviewQueueItemDetail",
    "ReviewQueueResponse",
    "VerificationContract",
    "VerificationResult",
    "VerificationSubmission",
]
