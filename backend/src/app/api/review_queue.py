from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.models.review_queue import (
    HumanReviewDecisionRequest,
    HumanReviewReceipt,
    ReviewQueueItemDetail,
    ReviewQueueResponse,
)
from app.review_queue.service import QueueConflictError, QueueNotFoundError, ReviewQueueRepository

router = APIRouter(prefix="/api/review-queue", tags=["review queue"])


@lru_cache
def get_review_queue_repository() -> ReviewQueueRepository:
    return ReviewQueueRepository()


def _not_found(error: QueueNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail="The requested queue item was not found.")


@router.get("", response_model=ReviewQueueResponse)
async def list_review_queue(
    repository: Annotated[ReviewQueueRepository, Depends(get_review_queue_repository)],
) -> ReviewQueueResponse:
    return repository.list()


@router.get("/{queue_item_id}", response_model=ReviewQueueItemDetail)
async def get_review_queue_item(
    queue_item_id: str,
    repository: Annotated[ReviewQueueRepository, Depends(get_review_queue_repository)],
) -> ReviewQueueItemDetail:
    try:
        return repository.detail(queue_item_id)
    except QueueNotFoundError as error:
        raise _not_found(error) from error


@router.get("/{queue_item_id}/images/{image_id}")
async def get_review_queue_image(
    queue_item_id: str,
    image_id: str,
    repository: Annotated[ReviewQueueRepository, Depends(get_review_queue_repository)],
) -> Response:
    try:
        return Response(
            content=repository.image_png(queue_item_id, image_id), media_type="image/png"
        )
    except QueueNotFoundError as error:
        raise _not_found(error) from error


@router.post("/{queue_item_id}/decision", response_model=HumanReviewReceipt)
async def decide_review_queue_item(
    queue_item_id: str,
    request: HumanReviewDecisionRequest,
    repository: Annotated[ReviewQueueRepository, Depends(get_review_queue_repository)],
) -> HumanReviewReceipt:
    try:
        return repository.decide(queue_item_id, request.decision, request.comment)
    except QueueConflictError as error:
        raise HTTPException(
            status_code=409, detail="This item has already left the active queue."
        ) from error


@router.post("/decisions/{decision_id}/undo", response_model=ReviewQueueItemDetail)
async def undo_review_decision(
    decision_id: str,
    repository: Annotated[ReviewQueueRepository, Depends(get_review_queue_repository)],
) -> ReviewQueueItemDetail:
    try:
        return repository.undo(decision_id)
    except QueueConflictError as error:
        raise HTTPException(status_code=409, detail="The undo window has expired.") from error
    except QueueNotFoundError as error:
        raise _not_found(error) from error
