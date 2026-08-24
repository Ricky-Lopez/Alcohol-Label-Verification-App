import asyncio
import json
from io import BytesIO
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.batches import get_batch_repository
from app.api.review_queue import get_review_queue_repository
from app.batch.service import BatchRepository, parse_batch_csv
from app.config import Settings, get_settings
from app.extraction.dependencies import get_ocr_extractor
from app.extraction.providers import MockOcrExtractor, MockScenario, ProviderImageExtraction
from app.main import app
from app.models.batch import BatchImageDeclaration
from app.models.label import ImageMediaType
from app.review_queue.service import ReviewQueueRepository, seed_queue

CSV_HEADER = (
    "record_id,filename,beverage_type,brand_name,class_type_designation,"
    "net_contents_value,net_contents_unit,alcohol_by_volume_percent,proof,"
    "producer_name,producer_city,producer_region,producer_country_code,imported,"
    "origin_country_code,origin_display_name\n"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def csv_row(record_id: str, filename: str, brand: str = "OLD TOM DISTILLERY") -> str:
    return (
        f"{record_id},{filename},distilled_spirits,{brand},"
        "Kentucky Straight Bourbon Whiskey,750,mL,45,90,Example Distilling Company,"
        "Frankfort,KY,US,false,,\n"
    )


def png_bytes(color: str = "white") -> bytes:
    output = BytesIO()
    Image.new("RGB", (48, 48), color).save(output, format="PNG")
    return output.getvalue()


def image_manifest(files: dict[str, bytes]) -> str:
    return json.dumps(
        {
            "images": [
                {"filename": name, "mediaType": "image/png", "sizeBytes": len(data)}
                for name, data in files.items()
            ]
        }
    )


def test_example_reviewer_queue_batch_matches_the_canonical_seed_values() -> None:
    csv_path = REPOSITORY_ROOT / "fixtures/applications/example-reviewer-queue-batch.csv"
    image_directory = REPOSITORY_ROOT / "fixtures/reviewer_queue"
    filenames = ["01-old-tom-distillery.png", "02-meadowlark-rye.png"]
    declarations = [
        BatchImageDeclaration(
            filename=filename,
            media_type=ImageMediaType.PNG,
            size_bytes=(image_directory / filename).stat().st_size,
        )
        for filename in filenames
    ]

    parsed, issues = parse_batch_csv(csv_path.read_text(encoding="utf-8"), declarations)
    seeds = seed_queue()[:2]

    assert issues == []
    assert [item.filename for item in parsed] == filenames
    assert [item.application.expected_label for item in parsed] == [
        seed.application.expected_label for seed in seeds
    ]


@pytest.fixture
def repositories() -> tuple[BatchRepository, ReviewQueueRepository]:
    return BatchRepository(), ReviewQueueRepository(records=seed_queue())


@pytest.fixture(autouse=True)
def override_dependencies(
    repositories: tuple[BatchRepository, ReviewQueueRepository],
) -> None:
    batch_repository, queue_repository = repositories
    app.dependency_overrides[get_batch_repository] = lambda: batch_repository
    app.dependency_overrides[get_review_queue_repository] = lambda: queue_repository
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_environment="test", ocr_provider="mock"
    )
    app.dependency_overrides[get_ocr_extractor] = MockOcrExtractor
    yield
    app.dependency_overrides.clear()


async def create_batch(client: AsyncClient, rows: str, files: dict[str, bytes]):
    return await client.post(
        "/api/batches",
        data={"images": image_manifest(files)},
        files={"applications": ("applications.csv", CSV_HEADER + rows, "text/csv")},
    )


async def process_item(
    client: AsyncClient,
    batch: dict[str, object],
    index: int,
    files: dict[str, bytes],
    scenario: str = "success",
):
    item = batch["items"][index]  # type: ignore[index]
    filename = item["filename"]
    return await client.post(
        f"/api/batches/{batch['batchId']}/items/{item['batchItemId']}/process",
        files={"image": (filename, files[filename], "image/png")},
        headers={"X-OCR-Mock-Scenario": scenario},
    )


@pytest.mark.anyio
async def test_complete_manifest_is_validated_before_any_work_starts() -> None:
    files = {"label-a.png": png_bytes()}
    rows = csv_row("batch-record-a", "missing.png")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await create_batch(client, rows, files)

    assert response.status_code == 422
    codes = {issue["code"] for issue in response.json()["issues"]}
    assert codes == {"missing_image", "unreferenced_image"}


@pytest.mark.anyio
async def test_csv_supports_bom_quoted_values_and_import_boolean_aliases() -> None:
    files = {"label-a.png": png_bytes()}
    header = CSV_HEADER.lstrip("\ufeff")
    row = (
        'imported-record,label-a.png,wine,"CHATEAU, EXAMPLE",Red Wine,750,mL,12,, '
        "Example Winery,Paris,,FR,yes,FR,France\n"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/batches",
            data={"images": image_manifest(files)},
            files={"applications": ("applications.csv", "\ufeff" + header + row, "text/csv")},
        )

    assert response.status_code == 201
    assert response.json()["items"][0]["brandName"] == "CHATEAU, EXAMPLE"


@pytest.mark.anyio
async def test_unknown_csv_columns_reject_the_batch() -> None:
    files = {"label-a.png": png_bytes()}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/batches",
            data={"images": image_manifest(files)},
            files={
                "applications": (
                    "applications.csv",
                    CSV_HEADER.rstrip() + ",unexpected\n" + csv_row(
                        "batch-record-a", "label-a.png"
                    ).rstrip() + ",value\n",
                    "text/csv",
                )
            },
        )

    assert response.status_code == 422
    assert "unknown_column" in {issue["code"] for issue in response.json()["issues"]}


@pytest.mark.anyio
async def test_batch_processes_items_and_preserves_csv_queue_order() -> None:
    files = {"label-a.png": png_bytes(), "label-b.png": png_bytes("gray")}
    rows = csv_row("batch-record-a", "label-a.png") + csv_row(
        "batch-record-b", "label-b.png", "SECOND BRAND"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await create_batch(client, rows, files)
        batch = created.json()
        second = await process_item(client, batch, 1, files)
        first = await process_item(client, second.json(), 0, files)
        queue = await client.get("/api/review-queue")
        export = await client.get(f"/api/batches/{batch['batchId']}/results.csv")

    assert created.status_code == 201
    assert first.json()["status"] == "completed"
    assert first.json()["readyCount"] == 2
    added = [item for item in queue.json()["items"] if item["recordId"].startswith("batch-record")]
    assert [item["recordId"] for item in added] == ["batch-record-a", "batch-record-b"]
    assert export.status_code == 200
    assert "batch-record-a,label-a.png" in export.text


@pytest.mark.anyio
async def test_failure_pauses_pending_work_until_retry_or_skip() -> None:
    files = {"label-a.png": png_bytes(), "label-b.png": png_bytes("gray")}
    rows = csv_row("batch-record-a", "label-a.png") + csv_row(
        "batch-record-b", "label-b.png"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await create_batch(client, rows, files)
        failed = await process_item(client, created.json(), 0, files, "timeout")
        blocked = await process_item(client, failed.json(), 1, files)
        item_id = failed.json()["items"][0]["batchItemId"]
        skipped = await client.post(
            f"/api/batches/{failed.json()['batchId']}/items/{item_id}/skip"
        )
        completed = await process_item(client, skipped.json(), 1, files)

    assert failed.status_code == 504
    assert failed.json()["status"] == "paused"
    assert blocked.status_code == 409
    assert skipped.json()["status"] == "processing"
    assert completed.json()["status"] == "completed_with_errors"
    assert completed.json()["skippedCount"] == 1
    assert completed.json()["readyCount"] == 1


@pytest.mark.anyio
async def test_failed_item_accepts_a_same_named_replacement_image() -> None:
    original = png_bytes()
    files = {"label-a.png": original}
    replacement = BytesIO()
    Image.new("RGB", (96, 96), "blue").save(replacement, format="PNG")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await create_batch(client, csv_row("batch-record-a", "label-a.png"), files)
        failed = await process_item(client, created.json(), 0, files, "timeout")
        item = failed.json()["items"][0]
        retried = await client.post(
            f"/api/batches/{failed.json()['batchId']}/items/{item['batchItemId']}/process",
            files={"image": ("label-a.png", replacement.getvalue(), "image/png")},
            headers={"X-OCR-Mock-Scenario": "success"},
        )

    assert len(replacement.getvalue()) != len(original)
    assert retried.status_code == 200
    assert retried.json()["status"] == "completed"


@pytest.mark.anyio
async def test_semantic_non_label_result_still_enters_human_review_queue() -> None:
    files = {"label-a.png": png_bytes()}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await create_batch(client, csv_row("batch-record-a", "label-a.png"), files)
        processed = await process_item(client, created.json(), 0, files, "not_label")

    item = processed.json()["items"][0]
    assert processed.status_code == 200
    assert item["status"] == "ready_for_review"
    assert item["overallStatus"] == "analysis_incomplete"
    assert item["queueItemId"]


class TrackingExtractor(MockOcrExtractor):
    active = 0
    maximum = 0

    async def extract_image(
        self,
        image,
        *,
        scenario: MockScenario | None = None,
    ) -> ProviderImageExtraction:
        type(self).active += 1
        type(self).maximum = max(type(self).maximum, type(self).active)
        try:
            await asyncio.sleep(0.02)
            return await super().extract_image(image, scenario=scenario)
        finally:
            type(self).active -= 1


@pytest.mark.anyio
async def test_batch_processing_is_bounded_to_three_concurrent_items() -> None:
    TrackingExtractor.active = 0
    TrackingExtractor.maximum = 0
    app.dependency_overrides[get_ocr_extractor] = TrackingExtractor
    files = {f"label-{index}.png": png_bytes() for index in range(4)}
    rows = "".join(
        csv_row(f"batch-record-{index}", filename)
        for index, filename in enumerate(files)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await create_batch(client, rows, files)
        batch = created.json()
        await asyncio.gather(
            *(process_item(client, batch, index, files) for index in range(4))
        )

    assert TrackingExtractor.maximum == 3
