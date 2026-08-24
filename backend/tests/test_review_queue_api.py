import json
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.review_queue import get_review_queue_repository
from app.main import app
from app.models.label import ImageMediaType, LabelImageInput, VerificationSubmission
from app.models.review_queue import ReviewQueueCreateRequest
from app.review_queue.service import ReviewQueueRepository, seed_queue


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 21, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


@pytest.fixture
def repository() -> ReviewQueueRepository:
    clock = Clock()
    return ReviewQueueRepository(records=seed_queue(clock), clock=clock)


@pytest.fixture(autouse=True)
def override_repository(repository: ReviewQueueRepository) -> None:
    app.dependency_overrides[get_review_queue_repository] = lambda: repository
    yield
    app.dependency_overrides.clear()


def queue_upload() -> tuple[ReviewQueueCreateRequest, bytes]:
    output = BytesIO()
    Image.new("RGB", (32, 32), "white").save(output, format="PNG")
    data = output.getvalue()
    seed = seed_queue()[0]
    application = seed.application.model_copy(update={"record_id": "ad-hoc-record-1"})
    verification = seed.verification.model_copy(
        update={"record_id": application.record_id, "submission_id": "ad-hoc-submission-1"}
    )
    image = LabelImageInput(
        client_image_id="queue-image",
        file_name="ad-hoc-label.png",
        media_type=ImageMediaType.PNG,
        size_bytes=len(data),
    )
    return (
        ReviewQueueCreateRequest(
            submission=VerificationSubmission(
                submission_id=verification.submission_id,
                application=application,
                images=[image],
            ),
            verification=verification,
        ),
        data,
    )


@pytest.mark.anyio
async def test_queue_lists_seeded_items_and_returns_details() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/review-queue")
        detail = await client.get("/api/review-queue/queue-item-1")
        image = await client.get("/api/review-queue/queue-item-1/images/queue-image-1")

    assert [item["position"] for item in response.json()["items"]] == [1, 2, 3, 4, 5, 6]
    assert response.json()["items"][2]["brandName"] == "STONE THROW"
    assert response.json()["items"][2]["overallStatus"] == "no_discrepancies_found"
    assert detail.json()["application"]["intakeSource"] == "batch"
    assert detail.json()["verification"]["decisionSupportOnly"] is True
    assert image.headers["content-type"].startswith("image/png")


@pytest.mark.anyio
async def test_processed_application_can_be_added_and_reviewed_without_rerunning_analysis() -> None:
    payload, data = queue_upload()
    multipart = {
        "payload": payload.model_dump_json(by_alias=True),
    }
    files = {"image": ("ad-hoc-label.png", data, "image/png")}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/review-queue", data=multipart, files=files)
        duplicate = await client.post("/api/review-queue", data=multipart, files=files)
        queue = await client.get("/api/review-queue")
        detail = await client.get(f"/api/review-queue/{created.json()['summary']['queueItemId']}")
        image = await client.get(created.json()["images"][0]["imageUrl"])

    assert created.status_code == 201
    assert duplicate.status_code == 201
    assert duplicate.json()["summary"]["queueItemId"] == created.json()["summary"]["queueItemId"]
    assert queue.json()["totalCount"] == 7
    assert created.json()["summary"]["position"] == 7
    assert detail.json()["application"] == payload.submission.application.model_dump(
        mode="json", by_alias=True
    )
    assert detail.json()["verification"] == payload.verification.model_dump(
        mode="json", by_alias=True
    )
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"


@pytest.mark.anyio
async def test_queue_rejects_mismatched_processed_application() -> None:
    payload, data = queue_upload()
    malformed = payload.model_dump(mode="json", by_alias=True)
    malformed["verification"]["recordId"] = "different-record"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/review-queue",
            data={"payload": json.dumps(malformed)},
            files={"image": ("ad-hoc-label.png", data, "image/png")},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_decision_removes_item_and_undo_restores_original_position(
    repository: ReviewQueueRepository,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        decision = await client.post(
            "/api/review-queue/queue-item-2/decision",
            json={"decision": "rejected", "comment": ""},
        )
        after_decision = await client.get("/api/review-queue")
        undo = await client.post(
            f"/api/review-queue/decisions/{decision.json()['decisionId']}/undo"
        )
        after_undo = await client.get("/api/review-queue")

    assert decision.status_code == 200
    assert decision.json()["comment"] is None
    assert decision.json()["remainingCount"] == 5
    assert [item["position"] for item in after_decision.json()["items"]] == [1, 3, 4, 5, 6]
    assert undo.status_code == 200
    assert [item["position"] for item in after_undo.json()["items"]] == [1, 2, 3, 4, 5, 6]


@pytest.mark.anyio
async def test_duplicate_decision_and_expired_undo_return_conflict(
    repository: ReviewQueueRepository,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        decision = await client.post(
            "/api/review-queue/queue-item-1/decision", json={"decision": "approved"}
        )
        duplicate = await client.post(
            "/api/review-queue/queue-item-1/decision", json={"decision": "approved"}
        )
        repository._clock.value += timedelta(seconds=11)  # type: ignore[attr-defined]
        expired = await client.post(
            f"/api/review-queue/decisions/{decision.json()['decisionId']}/undo"
        )

    assert duplicate.status_code == 409
    assert expired.status_code == 409
