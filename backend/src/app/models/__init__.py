"""Canonical domain contracts shared by API and verification modules."""

from app.models.contract import VerificationContract
from app.models.extraction import OcrExtractionResult
from app.models.label import ApplicationRecord, VerificationSubmission
from app.models.verification import ComparisonInput, VerificationResult

__all__ = [
    "ApplicationRecord",
    "ComparisonInput",
    "OcrExtractionResult",
    "VerificationContract",
    "VerificationResult",
    "VerificationSubmission",
]
