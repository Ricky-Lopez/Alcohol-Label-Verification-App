"""Session-scoped, synthetic reviewer queue for the prototype."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.comparison import compare
from app.extraction.image_processing import PreparedImage
from app.models.extraction import (
    ExtractedFieldCandidate,
    ExtractionIssue,
    ExtractionIssueCode,
    ExtractionStatus,
    ExtractionTiming,
    ExtractorReference,
    OcrExtractionResult,
    TextSegment,
    VerificationField,
)
from app.models.label import (
    AlcoholContent,
    ApplicationRecord,
    BeverageType,
    ImageMediaType,
    IntakeSource,
    LabelImageInput,
    LabelPanelType,
    NetContents,
    NetContentsUnit,
    PostalAddress,
    ResponsibleParty,
)
from app.models.review_queue import (
    HumanReviewDecision,
    HumanReviewReceipt,
    ReviewQueueImage,
    ReviewQueueItemDetail,
    ReviewQueueItemSummary,
    ReviewQueueResponse,
)
from app.models.verification import ComparisonInput, RulesetReference, VerificationResult
from app.rules import (
    GOVERNMENT_WARNING_TEXT,
    PROTOTYPE_RULESET_EFFECTIVE_DATE,
    PROTOTYPE_RULESET_ID,
    PROTOTYPE_RULESET_VERSION,
)

UNDO_WINDOW = timedelta(seconds=10)
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
QUEUE_IMAGE_DIRECTORY = REPOSITORY_ROOT / "fixtures" / "reviewer_queue"


class QueueNotFoundError(KeyError):
    pass


class QueueConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class QueueRecord:
    queue_item_id: str
    position: int
    application: ApplicationRecord
    verification: VerificationResult
    queued_at: datetime
    image_file_name: str | None = None
    image_data: bytes | None = None
    image_media_type: str = ImageMediaType.PNG.value
    source_image_id: str | None = None
    panel_type: LabelPanelType = LabelPanelType.BRAND
    version: int = 1

    @property
    def image_id(self) -> str:
        return self.source_image_id or f"queue-image-{self.position}"


@dataclass(frozen=True, slots=True)
class CompletedDecision:
    record: QueueRecord
    receipt: HumanReviewReceipt


def _now() -> datetime:
    return datetime.now(UTC)


def _ruleset() -> RulesetReference:
    return RulesetReference(
        ruleset_id=PROTOTYPE_RULESET_ID,
        version=PROTOTYPE_RULESET_VERSION,
        effective_date=PROTOTYPE_RULESET_EFFECTIVE_DATE,
        source_uri="docs/REQUIREMENTS.md#fr-016",
    )


def _application(
    position: int,
    brand: str,
    *,
    class_type_designation: str = "Kentucky Straight Bourbon Whiskey",
    abv_percent: int = 45,
    proof: int = 90,
    responsible_party_name: str = "Example Distilling Company",
    city: str = "Frankfort",
) -> ApplicationRecord:
    return ApplicationRecord(
        record_id=f"queue-application-{position}",
        intake_source=IntakeSource.BATCH,
        beverage_type=BeverageType.DISTILLED_SPIRITS,
        imported=False,
        expected_label={
            "brand_name": brand,
            "class_type_designation": class_type_designation,
            "alcohol_content": AlcoholContent(abv_percent=abv_percent, proof=proof),
            "net_contents": NetContents(value=750, unit=NetContentsUnit.MILLILITER),
            "responsible_parties": [
                ResponsibleParty(
                    name=responsible_party_name,
                    address=PostalAddress(city=city, region="KY", country_code="US"),
                )
            ],
        },
    )


def _candidate(
    field: VerificationField, text: str, index: int
) -> tuple[TextSegment, ExtractedFieldCandidate]:
    segment = TextSegment(
        segment_id=f"queue-segment-{index}", image_id="queue-image", raw_text=text
    )
    normalized = (
        "uppercase"
        if field == VerificationField.GOVERNMENT_WARNING_HEADING_CASE
        else "bold"
        if field == VerificationField.GOVERNMENT_WARNING_HEADING_WEIGHT
        else None
    )
    return segment, ExtractedFieldCandidate(
        field=field,
        raw_text=text,
        normalized_value=normalized,
        evidence_segment_ids=[segment.segment_id],
    )


def _verification(
    position: int, application: ApplicationRecord, scenario: str
) -> VerificationResult:
    entries = [
        (VerificationField.BRAND_NAME, application.expected_label.brand_name),
        (
            VerificationField.CLASS_TYPE_DESIGNATION,
            application.expected_label.class_type_designation,
        ),
        (
            VerificationField.ALCOHOL_CONTENT,
            f"{application.expected_label.alcohol_content.abv_percent}% Alc./Vol. "
            f"({application.expected_label.alcohol_content.proof} Proof)",
        ),
        (VerificationField.NET_CONTENTS, "750 mL"),
        (
            VerificationField.RESPONSIBLE_PARTY_NAME,
            application.expected_label.responsible_parties[0].name,
        ),
        (
            VerificationField.RESPONSIBLE_PARTY_ADDRESS,
            f"{application.expected_label.responsible_parties[0].address.city}, KY, USA",
        ),
        (VerificationField.GOVERNMENT_WARNING_TEXT, GOVERNMENT_WARNING_TEXT),
        (VerificationField.GOVERNMENT_WARNING_HEADING_CASE, "GOVERNMENT WARNING:"),
        (VerificationField.GOVERNMENT_WARNING_HEADING_WEIGHT, "GOVERNMENT WARNING:"),
    ]
    issues: list[ExtractionIssue] = []
    if scenario == "text_mismatch":
        entries[0] = (
            VerificationField.BRAND_NAME,
            application.expected_label.brand_name.replace("'", ""),
        )
    if scenario == "numeric_mismatch":
        entries[2] = (VerificationField.ALCOHOL_CONTENT, "44% Alc./Vol. (88 Proof)")
    if scenario == "warning_incomplete":
        entries[6] = (VerificationField.GOVERNMENT_WARNING_TEXT, GOVERNMENT_WARNING_TEXT[:120])
        issues.append(
            ExtractionIssue(
                code=ExtractionIssueCode.WARNING_TEXT_INCOMPLETE,
                message="The government warning text appears incomplete or unclear.",
                image_id="queue-image",
                field=VerificationField.GOVERNMENT_WARNING_TEXT,
            )
        )
    if scenario == "uncertain":
        issues.append(
            ExtractionIssue(
                code=ExtractionIssueCode.LABEL_CLASSIFICATION_UNCERTAIN,
                message="The image may contain an alcohol label, but classification is uncertain.",
                image_id="queue-image",
            )
        )
    pairs = [
        _candidate(field, text, position * 100 + index)
        for index, (field, text) in enumerate(entries, 1)
    ]
    extraction = OcrExtractionResult(
        extraction_id=f"queue-extraction-{position}",
        submission_id=f"queue-submission-{position}",
        status=ExtractionStatus.PARTIAL if issues else ExtractionStatus.SUCCEEDED,
        extractor=ExtractorReference(name="synthetic-queue-ocr", version="1.0"),
        duration_ms=1,
        timing=ExtractionTiming(image_preparation_ms=0, provider_ms=1),
        segments=[pair[0] for pair in pairs],
        field_candidates=[pair[1] for pair in pairs],
        issues=issues,
    )
    image = LabelImageInput(
        client_image_id="queue-image",
        file_name=f"queue-label-{position}.png",
        media_type=ImageMediaType.PNG,
        size_bytes=1,
    )
    return compare(
        ComparisonInput(
            comparison_id=f"queue-comparison-{position}",
            application=application,
            images=[image],
            extraction=extraction,
            ruleset=_ruleset(),
        )
    )


def seed_queue(clock: Callable[[], datetime] = _now) -> list[QueueRecord]:
    seeds = [
        ("OLD TOM DISTILLERY", "clear", "01-old-tom-distillery.png", {}),
        (
            "MEADOWLARK RYE",
            "clear",
            "02-meadowlark-rye.png",
            {
                "class_type_designation": "Straight Rye Whiskey",
                "abv_percent": 47,
                "proof": 94,
                "responsible_party_name": "Meadowlark Spirits",
                "city": "Lexington",
            },
        ),
        ("STONE THROW", "clear", "03-stones-throw.png", {}),
        ("RIVERBEND BOURBON", "numeric_mismatch", "04-riverbend-bourbon.png", {}),
        ("HARVEST MOON SPIRITS", "warning_incomplete", "05-harvest-moon-spirits.png", {}),
        ("CEDAR RIDGE WHISKEY", "uncertain", "06-cedar-ridge-whiskey.png", {}),
    ]
    queued_at = clock()
    records = []
    for position, (brand, scenario, image_file_name, application_values) in enumerate(seeds, 1):
        application = _application(position, brand, **application_values)
        records.append(
            QueueRecord(
                queue_item_id=f"queue-item-{position}",
                position=position,
                application=application,
                verification=_verification(position, application, scenario),
                queued_at=queued_at,
                image_file_name=image_file_name,
            )
        )
    return records


class ReviewQueueRepository:
    def __init__(
        self, records: list[QueueRecord] | None = None, clock: Callable[[], datetime] = _now
    ) -> None:
        self._clock, self._lock = clock, RLock()
        self._active = {record.queue_item_id: record for record in (records or seed_queue(clock))}
        self._completed: dict[str, CompletedDecision] = {}
        self._next_position = (
            max((record.position for record in self._active.values()), default=0) + 1
        )

    def _ordered(self) -> list[QueueRecord]:
        return sorted(self._active.values(), key=lambda item: item.position)

    def _summary(self, record: QueueRecord) -> ReviewQueueItemSummary:
        return ReviewQueueItemSummary(
            queue_item_id=record.queue_item_id,
            position=record.position,
            record_id=record.application.record_id,
            brand_name=record.application.expected_label.brand_name,
            beverage_type=record.application.beverage_type.value.replace("_", " "),
            overall_status=record.verification.overall_status,
            attention_count=sum(
                finding.severity.value in {"review", "discrepancy"}
                for finding in record.verification.findings
            ),
            queued_at=record.queued_at,
            version=record.version,
        )

    def list(self) -> ReviewQueueResponse:
        with self._lock:
            items = [self._summary(record) for record in self._ordered()]
            return ReviewQueueResponse(items=items, total_count=len(items))

    def detail(self, queue_item_id: str) -> ReviewQueueItemDetail:
        with self._lock:
            record = self._active.get(queue_item_id)
            if record is None:
                raise QueueNotFoundError(queue_item_id)
            image = ReviewQueueImage(
                image_id=record.image_id,
                panel_type=record.panel_type,
                alt_text=f"Submitted label for {record.application.expected_label.brand_name}",
                image_url=f"/api/review-queue/{record.queue_item_id}/images/{record.image_id}",
            )
            return ReviewQueueItemDetail(
                summary=self._summary(record),
                application=record.application,
                verification=record.verification,
                images=[image],
            )

    def image_content(self, queue_item_id: str, image_id: str) -> tuple[bytes, str]:
        with self._lock:
            record = self._active.get(queue_item_id)
            if record is None or image_id != record.image_id:
                raise QueueNotFoundError(queue_item_id)
            if record.image_data is not None:
                return record.image_data, record.image_media_type
            if record.image_file_name is None:
                raise QueueNotFoundError(queue_item_id)
            return (
                QUEUE_IMAGE_DIRECTORY / record.image_file_name
            ).read_bytes(), record.image_media_type

    def enqueue(
        self,
        *,
        application: ApplicationRecord,
        verification: VerificationResult,
        image: PreparedImage,
        panel_type: LabelPanelType,
    ) -> ReviewQueueItemDetail:
        with self._lock:
            existing = next(
                (
                    record
                    for record in self._active.values()
                    if record.application.record_id == application.record_id
                ),
                None,
            )
            if existing is not None:
                return self.detail(existing.queue_item_id)
            if any(
                completed.record.application.record_id == application.record_id
                for completed in self._completed.values()
            ):
                raise QueueConflictError(application.record_id)

            record = QueueRecord(
                queue_item_id=f"queue-item-{uuid4()}",
                position=self._next_position,
                application=application,
                verification=verification,
                queued_at=self._clock(),
                image_data=image.data,
                image_media_type=image.media_type,
                source_image_id=image.client_image_id,
                panel_type=panel_type,
            )
            self._next_position += 1
            self._active[record.queue_item_id] = record
            return self.detail(record.queue_item_id)

    def decide(
        self, queue_item_id: str, decision: HumanReviewDecision, comment: str | None
    ) -> HumanReviewReceipt:
        with self._lock:
            record = self._active.pop(queue_item_id, None)
            if record is None:
                raise QueueConflictError(queue_item_id)
            decided_at = self._clock()
            receipt = HumanReviewReceipt(
                decision_id=f"decision-{uuid4()}",
                queue_item_id=queue_item_id,
                decision=decision,
                comment=comment,
                decided_at=decided_at,
                undo_expires_at=decided_at + UNDO_WINDOW,
                remaining_count=len(self._active),
            )
            self._completed[receipt.decision_id] = CompletedDecision(record=record, receipt=receipt)
            return receipt

    def undo(self, decision_id: str) -> ReviewQueueItemDetail:
        with self._lock:
            completed = self._completed.pop(decision_id, None)
            if completed is None:
                raise QueueNotFoundError(decision_id)
            if self._clock() > completed.receipt.undo_expires_at:
                raise QueueConflictError(decision_id)
            self._active[completed.record.queue_item_id] = completed.record
            return self.detail(completed.record.queue_item_id)
