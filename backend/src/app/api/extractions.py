from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.extraction.dependencies import get_ocr_extractor
from app.extraction.image_processing import MAX_UPLOAD_BYTES, InvalidImageError, prepare_image
from app.extraction.providers import MockScenario, OcrExtractor
from app.extraction.service import run_extraction
from app.models.extraction import OcrExtractionResult
from app.models.label import VerificationSubmission

router = APIRouter(prefix="/api", tags=["extraction"])


@router.post(
    "/extractions",
    response_model=OcrExtractionResult,
    responses={
        502: {"model": OcrExtractionResult},
        503: {"model": OcrExtractionResult},
        504: {"model": OcrExtractionResult},
    },
)
async def create_extraction(
    submission_json: Annotated[str, Form(alias="submission")],
    images: Annotated[list[UploadFile], File()],
    extractor: Annotated[OcrExtractor, Depends(get_ocr_extractor)],
    settings: Annotated[Settings, Depends(get_settings)],
    mock_scenario: Annotated[
        MockScenario | None,
        Header(alias="X-OCR-Mock-Scenario"),
    ] = None,
) -> OcrExtractionResult | JSONResponse:
    if settings.ocr_provider != "mock" and mock_scenario is not None:
        raise HTTPException(
            status_code=422,
            detail="Mock OCR scenarios are available only with the mock provider.",
        )
    try:
        submission = VerificationSubmission.model_validate_json(submission_json)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail="The submission is invalid.") from error

    if len(images) != len(submission.images):
        raise HTTPException(
            status_code=422,
            detail="The number of uploaded images does not match the submission metadata.",
        )

    prepared_images = []
    for metadata, upload in zip(submission.images, images, strict=True):
        data = await upload.read(MAX_UPLOAD_BYTES + 1)
        await upload.close()
        try:
            prepared_images.append(
                prepare_image(
                    metadata,
                    upload_file_name=upload.filename,
                    upload_media_type=upload.content_type,
                    data=data,
                )
            )
        except InvalidImageError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    service_response = await run_extraction(
        extractor=extractor,
        submission_id=submission.submission_id,
        images=prepared_images,
        scenario=mock_scenario,
    )
    if service_response.http_status != 200:
        return JSONResponse(
            status_code=service_response.http_status,
            content=service_response.result.model_dump(mode="json", by_alias=True),
        )
    return service_response.result
