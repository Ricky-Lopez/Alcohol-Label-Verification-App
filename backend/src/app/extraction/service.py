import asyncio
from dataclasses import dataclass
from time import perf_counter
from uuid import uuid4

from app.extraction.image_processing import PreparedImage
from app.extraction.providers import (
    ExtractorConfigurationError,
    ExtractorInvalidResponseError,
    ExtractorRateLimitError,
    ExtractorRefusedError,
    ExtractorTimeoutError,
    ImageClassification,
    MockScenario,
    OcrExtractor,
    ProviderImageExtraction,
)
from app.models.extraction import (
    ExtractedFieldCandidate,
    ExtractionIssue,
    ExtractionIssueCode,
    ExtractionStatus,
    OcrExtractionResult,
    TextSegment,
    VerificationField,
)

MAX_CONCURRENT_EXTRACTIONS = 3


@dataclass(frozen=True, slots=True)
class ExtractionServiceResponse:
    result: OcrExtractionResult
    http_status: int


def _issue_for_error(error: BaseException, image_id: str) -> tuple[ExtractionIssue, int]:
    if isinstance(error, ExtractorTimeoutError):
        return (
            ExtractionIssue(
                code=ExtractionIssueCode.EXTRACTOR_TIMEOUT,
                message="Image analysis timed out. Try again.",
                image_id=image_id,
            ),
            504,
        )
    if isinstance(error, ExtractorConfigurationError):
        return (
            ExtractionIssue(
                code=ExtractionIssueCode.EXTRACTOR_UNAVAILABLE,
                message="Image analysis is not configured.",
                image_id=image_id,
            ),
            503,
        )
    if isinstance(error, ExtractorRateLimitError):
        return (
            ExtractionIssue(
                code=ExtractionIssueCode.EXTRACTOR_UNAVAILABLE,
                message="Image analysis is temporarily busy. Try again.",
                image_id=image_id,
            ),
            503,
        )
    if isinstance(error, ExtractorRefusedError):
        return (
            ExtractionIssue(
                code=ExtractionIssueCode.EXTRACTOR_REFUSED,
                message="The image analysis provider could not process this image.",
                image_id=image_id,
            ),
            502,
        )
    if isinstance(error, ExtractorInvalidResponseError):
        return (
            ExtractionIssue(
                code=ExtractionIssueCode.EXTRACTOR_INVALID_RESPONSE,
                message="Image analysis returned an unusable response. Try again.",
                image_id=image_id,
            ),
            502,
        )
    return (
        ExtractionIssue(
            code=ExtractionIssueCode.EXTRACTOR_UNAVAILABLE,
            message="Image analysis is temporarily unavailable. Try again.",
            image_id=image_id,
        ),
        502,
    )


def _map_provider_result(
    provider_result: ProviderImageExtraction,
    image: PreparedImage,
    *,
    image_index: int,
) -> tuple[list[TextSegment], list[ExtractedFieldCandidate], list[ExtractionIssue]]:
    if provider_result.classification == ImageClassification.NOT_ALCOHOL_LABEL:
        return (
            [],
            [],
            [
                ExtractionIssue(
                    code=ExtractionIssueCode.NOT_LABEL_IMAGE,
                    message="The image does not appear to contain an alcohol label.",
                    image_id=image.client_image_id,
                )
            ],
        )

    issues: list[ExtractionIssue] = []
    if provider_result.classification == ImageClassification.UNCERTAIN:
        issues.append(
            ExtractionIssue(
                code=ExtractionIssueCode.LABEL_CLASSIFICATION_UNCERTAIN,
                message="The image may contain an alcohol label, but classification is uncertain.",
                image_id=image.client_image_id,
            )
        )
    if provider_result.warning_text_incomplete:
        issues.append(
            ExtractionIssue(
                code=ExtractionIssueCode.WARNING_TEXT_INCOMPLETE,
                message="The government warning text appears incomplete or unclear.",
                image_id=image.client_image_id,
                field=VerificationField.GOVERNMENT_WARNING_TEXT,
            )
        )

    segment_ids = [
        f"segment-{image_index + 1}-{segment_index + 1}"
        for segment_index in range(len(provider_result.segments))
    ]
    segments = [
        TextSegment(
            segment_id=segment_id,
            image_id=image.client_image_id,
            raw_text=provider_segment.raw_text,
        )
        for segment_id, provider_segment in zip(segment_ids, provider_result.segments, strict=True)
    ]
    candidates: list[ExtractedFieldCandidate] = []
    for provider_candidate in provider_result.field_candidates:
        if provider_candidate.uncertain:
            issues.append(
                ExtractionIssue(
                    code=ExtractionIssueCode.LOW_CONFIDENCE,
                    message="The extracted field is uncertain and requires review.",
                    image_id=image.client_image_id,
                    field=provider_candidate.field,
                )
            )
        candidates.append(
            ExtractedFieldCandidate(
                field=provider_candidate.field,
                raw_text=provider_candidate.raw_text,
                normalized_value=provider_candidate.normalized_value,
                evidence_segment_ids=[
                    segment_ids[index] for index in provider_candidate.evidence_segment_indexes
                ],
            )
        )

    if not segments:
        issues.append(
            ExtractionIssue(
                code=ExtractionIssueCode.NO_TEXT_FOUND,
                message="No readable label text was found in the image.",
                image_id=image.client_image_id,
            )
        )
    return segments, candidates, issues


async def run_extraction(
    *,
    extractor: OcrExtractor,
    submission_id: str,
    images: list[PreparedImage],
    scenario: MockScenario | None = None,
) -> ExtractionServiceResponse:
    started = perf_counter()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)

    async def extract_one(image: PreparedImage) -> ProviderImageExtraction:
        async with semaphore:
            return await extractor.extract_image(image, scenario=scenario)

    attempts = await asyncio.gather(
        *(extract_one(image) for image in images),
        return_exceptions=True,
    )

    segments: list[TextSegment] = []
    candidates: list[ExtractedFieldCandidate] = []
    issues: list[ExtractionIssue] = []
    failure_statuses: list[int] = []

    for image_index, (image, attempt) in enumerate(zip(images, attempts, strict=True)):
        if isinstance(attempt, BaseException):
            issue, status = _issue_for_error(attempt, image.client_image_id)
            issues.append(issue)
            failure_statuses.append(status)
            continue
        try:
            image_segments, image_candidates, image_issues = _map_provider_result(
                attempt,
                image,
                image_index=image_index,
            )
        except (IndexError, ValueError):
            issue, status = _issue_for_error(ExtractorInvalidResponseError(), image.client_image_id)
            issues.append(issue)
            failure_statuses.append(status)
            continue
        segments.extend(image_segments)
        candidates.extend(image_candidates)
        issues.extend(image_issues)

    if segments and not issues:
        extraction_status = ExtractionStatus.SUCCEEDED
    elif segments:
        extraction_status = ExtractionStatus.PARTIAL
    else:
        extraction_status = ExtractionStatus.FAILED

    if segments or not failure_statuses:
        http_status = 200
    elif all(status == 504 for status in failure_statuses):
        http_status = 504
    elif any(status == 503 for status in failure_statuses):
        http_status = 503
    else:
        http_status = 502

    result = OcrExtractionResult(
        extraction_id=f"extraction-{uuid4()}",
        submission_id=submission_id,
        status=extraction_status,
        extractor=extractor.reference,
        duration_ms=round((perf_counter() - started) * 1000),
        segments=segments,
        field_candidates=candidates if extraction_status != ExtractionStatus.FAILED else [],
        issues=issues,
    )
    return ExtractionServiceResponse(result=result, http_status=http_status)
