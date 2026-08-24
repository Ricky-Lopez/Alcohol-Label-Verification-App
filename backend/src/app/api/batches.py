import asyncio
import csv
from functools import lru_cache
from io import StringIO
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from app.api.comparisons import active_ruleset
from app.api.review_queue import get_review_queue_repository
from app.batch.service import (
    BatchConflictError,
    BatchNotFoundError,
    BatchRepository,
    parse_batch_csv,
)
from app.comparison import compare
from app.config import Settings, get_settings
from app.extraction.dependencies import get_ocr_extractor
from app.extraction.image_processing import MAX_UPLOAD_BYTES, InvalidImageError, prepare_image
from app.extraction.providers import MockScenario, OcrExtractor
from app.extraction.service import run_extraction
from app.models.batch import (
    BatchDetail,
    BatchImageManifest,
    BatchValidationIssue,
    BatchValidationResponse,
)
from app.models.label import ImageMediaType, LabelImageInput
from app.models.verification import ComparisonInput
from app.review_queue.service import QueueConflictError, ReviewQueueRepository

router = APIRouter(prefix="/api/batches", tags=["batch application input"])
BATCH_PROCESSING_LIMIT = 3
_processing_semaphore = asyncio.Semaphore(BATCH_PROCESSING_LIMIT)


@lru_cache
def get_batch_repository() -> BatchRepository:
    return BatchRepository()


def _not_found(error: BatchNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail="The requested batch or batch item was not found.")


def _conflict(error: BatchConflictError | QueueConflictError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(error))


def _batch_response(detail: BatchDetail, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=detail.model_dump(mode="json", by_alias=True),
    )


@router.post(
    "",
    response_model=BatchDetail,
    status_code=201,
    responses={422: {"model": BatchValidationResponse}},
)
async def create_batch(
    applications: Annotated[UploadFile, File()],
    image_manifest_json: Annotated[str, Form(alias="images")],
    repository: Annotated[BatchRepository, Depends(get_batch_repository)],
    queue_repository: Annotated[
        ReviewQueueRepository, Depends(get_review_queue_repository)
    ],
) -> BatchDetail | JSONResponse:
    if not applications.filename or not applications.filename.casefold().endswith(".csv"):
        await applications.close()
        response = BatchValidationResponse(
            message="The batch could not be validated.",
            issues=[
                BatchValidationIssue(
                    code="invalid_csv_file", message="Choose a file with a .csv extension."
                )
            ],
        )
        return JSONResponse(
            status_code=422,
            content=response.model_dump(mode="json", by_alias=True),
        )
    try:
        manifest = BatchImageManifest.model_validate_json(image_manifest_json)
    except ValidationError:
        response = BatchValidationResponse(
            message="The selected image manifest is invalid.",
            issues=[
                BatchValidationIssue(
                    code="invalid_image_manifest",
                    message="Choose between 1 and 200 non-empty JPEG or PNG images under 20 MB.",
                )
            ],
        )
        return JSONResponse(
            status_code=422,
            content=response.model_dump(mode="json", by_alias=True),
        )

    csv_bytes = await applications.read(2_000_001)
    await applications.close()
    if len(csv_bytes) > 2_000_000:
        response = BatchValidationResponse(
            message="The batch could not be validated.",
            issues=[
                BatchValidationIssue(
                    code="csv_too_large", message="The CSV file exceeds the 2 MB limit."
                )
            ],
        )
        return JSONResponse(
            status_code=422,
            content=response.model_dump(mode="json", by_alias=True),
        )
    try:
        csv_text = csv_bytes.decode("utf-8")
    except UnicodeDecodeError:
        response = BatchValidationResponse(
            message="The batch could not be validated.",
            issues=[
                BatchValidationIssue(
                    code="invalid_encoding", message="The CSV file must use UTF-8 encoding."
                )
            ],
        )
        return JSONResponse(
            status_code=422,
            content=response.model_dump(mode="json", by_alias=True),
        )

    existing_ids = repository.record_ids()
    existing_ids.update(item.record_id for item in queue_repository.list().items)
    parsed, issues = parse_batch_csv(
        csv_text,
        manifest.images,
        existing_record_ids=existing_ids,
    )
    if issues:
        response = BatchValidationResponse(
            message="Correct every CSV and image error before processing the batch.",
            issues=issues,
        )
        return JSONResponse(
            status_code=422,
            content=response.model_dump(mode="json", by_alias=True),
        )
    positions = queue_repository.reserve_positions(len(parsed))
    return repository.create(parsed, positions)


@router.get("/{batch_id}", response_model=BatchDetail)
async def get_batch(
    batch_id: str,
    repository: Annotated[BatchRepository, Depends(get_batch_repository)],
) -> BatchDetail:
    try:
        return repository.detail(batch_id)
    except BatchNotFoundError as error:
        raise _not_found(error) from error


@router.post(
    "/{batch_id}/items/{item_id}/process",
    response_model=BatchDetail,
    responses={
        422: {"model": BatchDetail},
        502: {"model": BatchDetail},
        503: {"model": BatchDetail},
        504: {"model": BatchDetail},
    },
)
async def process_batch_item(
    batch_id: str,
    item_id: str,
    image: Annotated[UploadFile, File()],
    extractor: Annotated[OcrExtractor, Depends(get_ocr_extractor)],
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[BatchRepository, Depends(get_batch_repository)],
    queue_repository: Annotated[
        ReviewQueueRepository, Depends(get_review_queue_repository)
    ],
    mock_scenario: Annotated[
        MockScenario | None, Header(alias="X-OCR-Mock-Scenario")
    ] = None,
) -> BatchDetail | JSONResponse:
    started = perf_counter()
    if settings.ocr_provider != "mock" and mock_scenario is not None:
        raise HTTPException(
            status_code=422,
            detail="Mock OCR scenarios are available only with the mock provider.",
        )

    async with _processing_semaphore:
        try:
            submission, comparison_id, queue_position, is_retry = repository.start_processing(
                batch_id, item_id
            )
        except BatchNotFoundError as error:
            await image.close()
            raise _not_found(error) from error
        except BatchConflictError as error:
            await image.close()
            raise _conflict(error) from error

        metadata = submission.images[0]
        data = await image.read(MAX_UPLOAD_BYTES + 1)
        await image.close()
        if is_retry:
            try:
                replacement_metadata = LabelImageInput(
                    client_image_id=submission.images[0].client_image_id,
                    file_name=submission.images[0].file_name,
                    media_type=ImageMediaType(image.content_type),
                    size_bytes=len(data),
                    panel_type=submission.images[0].panel_type,
                )
                submission = repository.replace_image_metadata(
                    batch_id, item_id, replacement_metadata
                )
                metadata = submission.images[0]
            except (TypeError, ValueError, ValidationError):
                pass
        try:
            prepared = prepare_image(
                metadata,
                upload_file_name=image.filename,
                upload_media_type=image.content_type,
                data=data,
            )
        except InvalidImageError as error:
            detail = repository.fail(
                batch_id,
                item_id,
                code="invalid_image",
                message=str(error),
                duration_ms=round((perf_counter() - started) * 1000),
            )
            return _batch_response(detail, 422)

        try:
            extraction_response = await run_extraction(
                extractor=extractor,
                submission_id=submission.submission_id,
                images=[prepared],
                scenario=mock_scenario,
                request_started=started,
            )
            if extraction_response.http_status != 200:
                message = (
                    extraction_response.result.issues[0].message
                    if extraction_response.result.issues
                    else "Image analysis failed. Try again."
                )
                detail = repository.fail(
                    batch_id,
                    item_id,
                    code=f"ocr_{extraction_response.http_status}",
                    message=message,
                    duration_ms=extraction_response.result.duration_ms,
                )
                return _batch_response(detail, extraction_response.http_status)

            verification = compare(
                ComparisonInput(
                    comparison_id=comparison_id,
                    application=submission.application,
                    images=submission.images,
                    extraction=extraction_response.result,
                    ruleset=active_ruleset(),
                )
            )
            try:
                queued = queue_repository.enqueue(
                    application=submission.application,
                    verification=verification,
                    image=prepared,
                    panel_type=metadata.panel_type,
                    position=queue_position,
                )
            except QueueConflictError:
                detail = repository.fail(
                    batch_id,
                    item_id,
                    code="queue_conflict",
                    message="This record has already completed human review.",
                    duration_ms=round((perf_counter() - started) * 1000),
                )
                return _batch_response(detail, 409)
            return repository.finish_success(
                batch_id,
                item_id,
                overall_status=verification.overall_status,
                queue_item_id=queued.summary.queue_item_id,
                duration_ms=round((perf_counter() - started) * 1000),
            )
        except Exception:
            detail = repository.fail(
                batch_id,
                item_id,
                code="processing_error",
                message="The application could not be processed. Try again.",
                duration_ms=round((perf_counter() - started) * 1000),
            )
            return _batch_response(detail, 500)


@router.post("/{batch_id}/items/{item_id}/skip", response_model=BatchDetail)
async def skip_batch_item(
    batch_id: str,
    item_id: str,
    repository: Annotated[BatchRepository, Depends(get_batch_repository)],
) -> BatchDetail:
    try:
        return repository.skip(batch_id, item_id)
    except BatchNotFoundError as error:
        raise _not_found(error) from error
    except BatchConflictError as error:
        raise _conflict(error) from error


@router.get("/{batch_id}/results.csv")
async def download_batch_results(
    batch_id: str,
    repository: Annotated[BatchRepository, Depends(get_batch_repository)],
) -> Response:
    try:
        detail = repository.detail(batch_id)
    except BatchNotFoundError as error:
        raise _not_found(error) from error
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "row_number",
            "record_id",
            "filename",
            "brand_name",
            "processing_status",
            "automated_result",
            "queue_item_id",
            "error_code",
            "error_message",
            "duration_ms",
        ]
    )
    for item in detail.items:
        writer.writerow(
            [
                item.row_number,
                item.record_id,
                item.filename,
                item.brand_name,
                item.status.value,
                item.overall_status.value if item.overall_status else "",
                item.queue_item_id or "",
                item.error_code or "",
                item.error_message or "",
                item.duration_ms if item.duration_ms is not None else "",
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{batch_id}-results.csv"'
        },
    )
