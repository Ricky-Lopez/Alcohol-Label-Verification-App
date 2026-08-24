"""Session-scoped batch manifest validation and processing state."""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import PurePath
from threading import RLock
from uuid import uuid4

from pydantic import ValidationError

from app.models.batch import (
    BatchDetail,
    BatchImageDeclaration,
    BatchItemStatus,
    BatchItemSummary,
    BatchStatus,
    BatchValidationIssue,
)
from app.models.label import (
    AlcoholContent,
    ApplicationRecord,
    BeverageType,
    CountryOfOrigin,
    ExpectedLabelFields,
    IntakeSource,
    LabelImageInput,
    LabelPanelType,
    NetContents,
    NetContentsUnit,
    PostalAddress,
    ResponsibleParty,
    VerificationSubmission,
)
from app.models.verification import OverallReviewStatus

MAX_BATCH_ITEMS = 200
REQUIRED_COLUMNS = {
    "record_id",
    "filename",
    "beverage_type",
    "brand_name",
    "class_type_designation",
    "net_contents_value",
    "net_contents_unit",
    "producer_name",
    "producer_city",
    "producer_country_code",
    "imported",
}
OPTIONAL_COLUMNS = {
    "alcohol_by_volume_percent",
    "proof",
    "producer_region",
    "origin_country_code",
    "origin_display_name",
}
ALLOWED_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS
TRUE_VALUES = {"true", "yes", "1"}
FALSE_VALUES = {"false", "no", "0"}


class BatchNotFoundError(KeyError):
    pass


class BatchConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedBatchItem:
    row_number: int
    filename: str
    application: ApplicationRecord
    image: BatchImageDeclaration


@dataclass(slots=True)
class BatchItemRecord:
    batch_item_id: str
    row_number: int
    filename: str
    application: ApplicationRecord
    image_metadata: LabelImageInput
    submission_id: str
    comparison_id: str
    queue_position: int
    status: BatchItemStatus = BatchItemStatus.PENDING
    overall_status: OverallReviewStatus | None = None
    queue_item_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    duration_ms: int | None = None

    def submission(self) -> VerificationSubmission:
        return VerificationSubmission(
            submission_id=self.submission_id,
            application=self.application,
            images=[self.image_metadata],
        )


@dataclass(slots=True)
class BatchRecord:
    batch_id: str
    created_at: datetime
    items: list[BatchItemRecord]
    status: BatchStatus = BatchStatus.PROCESSING
    completed_at: datetime | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _issue(
    code: str, message: str, *, row: int | None = None, field: str | None = None
) -> BatchValidationIssue:
    return BatchValidationIssue(code=code, message=message, row=row, field=field)


def _parse_boolean(value: str) -> bool | None:
    normalized = value.strip().casefold()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return None


def _optional_number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return float(value.strip())


def _build_application(row: dict[str, str], row_number: int) -> ApplicationRecord:
    imported = _parse_boolean(row["imported"])
    if imported is None:
        raise ValueError("imported must be true, false, yes, no, 1, or 0")
    beverage_type = BeverageType(row["beverage_type"].strip())
    abv = _optional_number(row.get("alcohol_by_volume_percent"))
    proof = _optional_number(row.get("proof"))
    alcohol = AlcoholContent(abv_percent=abv, proof=proof) if abv is not None else None
    origin_code = (row.get("origin_country_code") or "").strip().upper()
    origin_name = (row.get("origin_display_name") or "").strip()
    if imported and (not origin_code or not origin_name):
        raise ValueError(
            "origin_country_code and origin_display_name are required for imported products"
        )
    return ApplicationRecord(
        record_id=row["record_id"].strip(),
        intake_source=IntakeSource.BATCH,
        beverage_type=beverage_type,
        imported=imported,
        expected_label=ExpectedLabelFields(
            brand_name=row["brand_name"].strip(),
            class_type_designation=row["class_type_designation"].strip(),
            alcohol_content=alcohol,
            net_contents=NetContents(
                value=float(row["net_contents_value"].strip()),
                unit=NetContentsUnit(row["net_contents_unit"].strip()),
            ),
            responsible_parties=[
                ResponsibleParty(
                    name=row["producer_name"].strip(),
                    address=PostalAddress(
                        city=row["producer_city"].strip(),
                        region=(row.get("producer_region") or "").strip() or None,
                        country_code=row["producer_country_code"].strip().upper(),
                    ),
                )
            ],
            country_of_origin=(
                CountryOfOrigin(country_code=origin_code, display_name=origin_name)
                if imported
                else None
            ),
        ),
    )


def parse_batch_csv(
    text: str,
    images: list[BatchImageDeclaration],
    *,
    existing_record_ids: set[str] | None = None,
) -> tuple[list[ParsedBatchItem], list[BatchValidationIssue]]:
    issues: list[BatchValidationIssue] = []
    try:
        reader = csv.DictReader(StringIO(text.lstrip("\ufeff")), strict=True)
        headers = reader.fieldnames or []
        rows = list(reader)
    except (csv.Error, UnicodeError):
        return [], [_issue("invalid_csv", "The CSV file could not be parsed.")]

    duplicate_headers = sorted({header for header in headers if headers.count(header) > 1})
    for header in duplicate_headers:
        issues.append(_issue("duplicate_column", f"Column '{header}' appears more than once."))
    for column in sorted(REQUIRED_COLUMNS - set(headers)):
        issues.append(_issue("missing_column", f"Required column '{column}' is missing."))
    for column in sorted(set(headers) - ALLOWED_COLUMNS):
        issues.append(_issue("unknown_column", f"Unknown column '{column}' is not supported."))
    if not rows:
        issues.append(_issue("empty_batch", "The CSV must contain at least one application row."))
    if len(rows) > MAX_BATCH_ITEMS:
        issues.append(_issue("batch_too_large", "A batch may contain no more than 200 rows."))

    declaration_names = [image.filename for image in images]
    duplicate_declarations = {
        name for name in declaration_names if declaration_names.count(name) > 1
    }
    for filename in sorted(duplicate_declarations):
        issues.append(
            _issue("duplicate_image", f"Image filename '{filename}' was selected more than once.")
        )
    image_by_name = {image.filename: image for image in images}
    seen_records: set[str] = set()
    seen_filenames: set[str] = set()
    parsed: list[ParsedBatchItem] = []

    if issues and (REQUIRED_COLUMNS - set(headers) or set(headers) - ALLOWED_COLUMNS):
        return [], issues

    for index, raw_row in enumerate(rows, start=2):
        row = {key: (value or "").strip() for key, value in raw_row.items() if key is not None}
        if None in raw_row:
            issues.append(
                _issue("extra_value", "The row contains more values than the header.", row=index)
            )
        for column in REQUIRED_COLUMNS:
            if not row.get(column):
                issues.append(
                    _issue(
                        "required_value",
                        f"'{column}' is required.",
                        row=index,
                        field=column,
                    )
                )
        record_id = row.get("record_id", "")
        filename = row.get("filename", "")
        if record_id in seen_records:
            issues.append(
                _issue(
                    "duplicate_record_id",
                    f"Record ID '{record_id}' appears more than once.",
                    row=index,
                    field="record_id",
                )
            )
        if record_id and record_id in (existing_record_ids or set()):
            issues.append(
                _issue(
                    "record_already_exists",
                    f"Record ID '{record_id}' is already active.",
                    row=index,
                    field="record_id",
                )
            )
        if filename in seen_filenames:
            issues.append(
                _issue(
                    "duplicate_filename",
                    f"Filename '{filename}' appears more than once.",
                    row=index,
                    field="filename",
                )
            )
        if filename and PurePath(filename).name != filename:
            issues.append(
                _issue(
                    "invalid_filename",
                    "filename must be a basename without a directory path.",
                    row=index,
                    field="filename",
                )
            )
        if filename and filename not in image_by_name:
            issues.append(
                _issue(
                    "missing_image",
                    f"No selected image exactly matches '{filename}'.",
                    row=index,
                    field="filename",
                )
            )
        seen_records.add(record_id)
        seen_filenames.add(filename)
        if any(issue.row == index for issue in issues):
            continue
        try:
            application = _build_application(row, index)
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            issues.append(
                _issue(
                    "invalid_application",
                    str(error).splitlines()[0][:255],
                    row=index,
                )
            )
            continue
        parsed.append(
            ParsedBatchItem(
                row_number=index,
                filename=filename,
                application=application,
                image=image_by_name[filename],
            )
        )

    for filename in sorted(set(declaration_names) - seen_filenames):
        issues.append(
            _issue("unreferenced_image", f"Selected image '{filename}' is not used by the CSV.")
        )
    return (parsed if not issues else []), issues


class BatchRepository:
    def __init__(self, clock: Callable[[], datetime] = _now) -> None:
        self._clock = clock
        self._lock = RLock()
        self._batches: dict[str, BatchRecord] = {}

    def record_ids(self) -> set[str]:
        with self._lock:
            return {
                item.application.record_id
                for batch in self._batches.values()
                for item in batch.items
                if item.status != BatchItemStatus.SKIPPED
            }

    def create(self, parsed: list[ParsedBatchItem], positions: list[int]) -> BatchDetail:
        with self._lock:
            batch_id = f"batch-{uuid4()}"
            items = [
                BatchItemRecord(
                    batch_item_id=f"batch-item-{uuid4()}",
                    row_number=item.row_number,
                    filename=item.filename,
                    application=item.application,
                    image_metadata=LabelImageInput(
                        client_image_id=f"batch-image-{uuid4()}",
                        file_name=item.filename,
                        media_type=item.image.media_type,
                        size_bytes=item.image.size_bytes,
                        panel_type=LabelPanelType.UNKNOWN,
                    ),
                    submission_id=f"batch-submission-{uuid4()}",
                    comparison_id=f"batch-comparison-{uuid4()}",
                    queue_position=position,
                )
                for item, position in zip(parsed, positions, strict=True)
            ]
            record = BatchRecord(batch_id=batch_id, created_at=self._clock(), items=items)
            self._batches[batch_id] = record
            return self._detail(record)

    def _get(self, batch_id: str) -> BatchRecord:
        record = self._batches.get(batch_id)
        if record is None:
            raise BatchNotFoundError(batch_id)
        return record

    def _item(self, record: BatchRecord, item_id: str) -> BatchItemRecord:
        item = next((item for item in record.items if item.batch_item_id == item_id), None)
        if item is None:
            raise BatchNotFoundError(item_id)
        return item

    def _refresh_status(self, record: BatchRecord) -> None:
        statuses = {item.status for item in record.items}
        if BatchItemStatus.FAILED in statuses:
            record.status = BatchStatus.PAUSED
            record.completed_at = None
        elif statuses <= {BatchItemStatus.READY_FOR_REVIEW, BatchItemStatus.SKIPPED}:
            record.status = (
                BatchStatus.COMPLETED_WITH_ERRORS
                if BatchItemStatus.SKIPPED in statuses
                else BatchStatus.COMPLETED
            )
            record.completed_at = record.completed_at or self._clock()
        else:
            record.status = BatchStatus.PROCESSING
            record.completed_at = None

    def _detail(self, record: BatchRecord) -> BatchDetail:
        items = [
            BatchItemSummary(
                batch_item_id=item.batch_item_id,
                row_number=item.row_number,
                filename=item.filename,
                record_id=item.application.record_id,
                brand_name=item.application.expected_label.brand_name,
                status=item.status,
                overall_status=item.overall_status,
                queue_item_id=item.queue_item_id,
                error_code=item.error_code,
                error_message=item.error_message,
                retryable=item.retryable,
                duration_ms=item.duration_ms,
            )
            for item in record.items
        ]
        ready = sum(item.status == BatchItemStatus.READY_FOR_REVIEW for item in record.items)
        failed = sum(item.status == BatchItemStatus.FAILED for item in record.items)
        skipped = sum(item.status == BatchItemStatus.SKIPPED for item in record.items)
        processed = ready + failed + skipped
        return BatchDetail(
            batch_id=record.batch_id,
            status=record.status,
            total_count=len(record.items),
            processed_count=processed,
            ready_count=ready,
            failed_count=failed,
            skipped_count=skipped,
            created_at=record.created_at,
            completed_at=record.completed_at,
            items=items,
        )

    def detail(self, batch_id: str) -> BatchDetail:
        with self._lock:
            return self._detail(self._get(batch_id))

    def start_processing(
        self, batch_id: str, item_id: str
    ) -> tuple[VerificationSubmission, str, int, bool]:
        with self._lock:
            record = self._get(batch_id)
            item = self._item(record, item_id)
            unresolved = [
                candidate
                for candidate in record.items
                if candidate.status == BatchItemStatus.FAILED
            ]
            if unresolved and item.status != BatchItemStatus.FAILED:
                raise BatchConflictError("The batch is paused until failed items are resolved.")
            if item.status not in {BatchItemStatus.PENDING, BatchItemStatus.FAILED}:
                raise BatchConflictError("The batch item cannot be processed in its current state.")
            is_retry = item.status == BatchItemStatus.FAILED
            item.status = BatchItemStatus.PROCESSING
            item.error_code = None
            item.error_message = None
            item.retryable = False
            self._refresh_status(record)
            return item.submission(), item.comparison_id, item.queue_position, is_retry

    def replace_image_metadata(
        self, batch_id: str, item_id: str, image_metadata: LabelImageInput
    ) -> VerificationSubmission:
        with self._lock:
            record = self._get(batch_id)
            item = self._item(record, item_id)
            if item.status != BatchItemStatus.PROCESSING:
                raise BatchConflictError("The batch item is not processing.")
            item.image_metadata = image_metadata
            return item.submission()

    def finish_success(
        self,
        batch_id: str,
        item_id: str,
        *,
        overall_status: OverallReviewStatus,
        queue_item_id: str,
        duration_ms: int,
    ) -> BatchDetail:
        with self._lock:
            record = self._get(batch_id)
            item = self._item(record, item_id)
            if item.status != BatchItemStatus.PROCESSING:
                raise BatchConflictError("The batch item is not processing.")
            item.status = BatchItemStatus.READY_FOR_REVIEW
            item.overall_status = overall_status
            item.queue_item_id = queue_item_id
            item.duration_ms = duration_ms
            self._refresh_status(record)
            return self._detail(record)

    def fail(
        self,
        batch_id: str,
        item_id: str,
        *,
        code: str,
        message: str,
        duration_ms: int,
    ) -> BatchDetail:
        with self._lock:
            record = self._get(batch_id)
            item = self._item(record, item_id)
            item.status = BatchItemStatus.FAILED
            item.error_code = code
            item.error_message = message[:255]
            item.retryable = True
            item.duration_ms = duration_ms
            self._refresh_status(record)
            return self._detail(record)

    def skip(self, batch_id: str, item_id: str) -> BatchDetail:
        with self._lock:
            record = self._get(batch_id)
            item = self._item(record, item_id)
            if item.status != BatchItemStatus.FAILED:
                raise BatchConflictError("Only failed batch items can be skipped.")
            item.status = BatchItemStatus.SKIPPED
            item.retryable = False
            self._refresh_status(record)
            return self._detail(record)
