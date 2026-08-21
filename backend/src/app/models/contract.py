from app.models.base import ContractModel
from app.models.extraction import OcrExtractionResult
from app.models.label import SubmissionTransport, VerificationSubmission
from app.models.verification import ComparisonInput, ComparisonRequest, VerificationResult


class VerificationContract(ContractModel):
    """Schema bundle used to generate frontend boundary types."""

    submission: VerificationSubmission
    submission_transport: SubmissionTransport
    extraction: OcrExtractionResult
    comparison_input: ComparisonInput
    comparison_request: ComparisonRequest
    result: VerificationResult
