from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.review_queue import get_review_queue_repository
from app.main import app
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


@pytest.mark.anyio
async def test_queue_lists_seeded_items_and_returns_details() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/review-queue")
        detail = await client.get("/api/review-queue/queue-item-1")
        image = await client.get("/api/review-queue/queue-item-1/images/queue-image-1")

    assert [item["position"] for item in response.json()["items"]] == [1, 2, 3, 4, 5, 6]
    assert detail.json()["application"]["intakeSource"] == "batch"
    assert detail.json()["verification"]["decisionSupportOnly"] is True
    assert image.headers["content-type"].startswith("image/png")


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
