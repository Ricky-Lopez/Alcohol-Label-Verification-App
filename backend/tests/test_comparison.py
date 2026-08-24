from app.comparison import compare
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
    CountryOfOrigin,
    ExpectedLabelFields,
    ImageMediaType,
    IntakeSource,
    LabelImageInput,
    NetContents,
    NetContentsUnit,
    PostalAddress,
    ResponsibleParty,
)
from app.models.verification import (
    ComparisonInput,
    OverallReviewStatus,
    RulesetReference,
    VerificationOutcome,
)
from app.rules import (
    GOVERNMENT_WARNING_TEXT,
    PROTOTYPE_RULESET_EFFECTIVE_DATE,
    PROTOTYPE_RULESET_ID,
    PROTOTYPE_RULESET_VERSION,
)


def application(
    *, imported: bool = False, alcohol: AlcoholContent | None = None
) -> ApplicationRecord:
    return ApplicationRecord(
        record_id="application-1",
        intake_source=IntakeSource.AD_HOC,
        beverage_type=BeverageType.DISTILLED_SPIRITS,
        imported=imported,
        expected_label=ExpectedLabelFields(
            brand_name="Stone's Throw",
            class_type_designation="Kentucky Straight Bourbon Whiskey",
            alcohol_content=alcohol or AlcoholContent(abv_percent=45, proof=90),
            net_contents=NetContents(value=0.75, unit=NetContentsUnit.LITER),
            responsible_parties=[
                ResponsibleParty(
                    name="Example Distilling Company",
                    address=PostalAddress(city="Frankfort", region="KY", country_code="US"),
                )
            ],
            country_of_origin=(
                CountryOfOrigin(country_code="GB", display_name="United Kingdom")
                if imported
                else None
            ),
        ),
    )


def candidate(
    field: VerificationField, text: str, index: int
) -> tuple[TextSegment, ExtractedFieldCandidate]:
    segment = TextSegment(segment_id=f"segment-{index}", image_id="image-1", raw_text=text)
    return segment, ExtractedFieldCandidate(
        field=field,
        raw_text=text,
        normalized_value=(
            "uppercase" if field == VerificationField.GOVERNMENT_WARNING_HEADING_CASE else None
        ),
        evidence_segment_ids=[segment.segment_id],
    )


def comparison_input(
    entries: list[tuple[VerificationField, str]],
    *,
    imported: bool = False,
    issues: list[ExtractionIssue] | None = None,
) -> ComparisonInput:
    pairs = [candidate(field, text, index) for index, (field, text) in enumerate(entries, 1)]
    extraction = OcrExtractionResult(
        extraction_id="extraction-1",
        submission_id="submission-1",
        status=ExtractionStatus.PARTIAL if issues else ExtractionStatus.SUCCEEDED,
        extractor=ExtractorReference(name="mock", version="1"),
        duration_ms=1,
        timing=ExtractionTiming(image_preparation_ms=0, provider_ms=1),
        segments=[pair[0] for pair in pairs],
        field_candidates=[pair[1] for pair in pairs],
        issues=issues or [],
    )
    return ComparisonInput(
        comparison_id="comparison-1",
        application=application(imported=imported),
        images=[
            LabelImageInput(
                client_image_id="image-1",
                file_name="label.png",
                media_type=ImageMediaType.PNG,
                size_bytes=1,
            )
        ],
        extraction=extraction,
        ruleset=RulesetReference(
            ruleset_id=PROTOTYPE_RULESET_ID,
            version=PROTOTYPE_RULESET_VERSION,
            effective_date=PROTOTYPE_RULESET_EFFECTIVE_DATE,
        ),
    )


def finding(result, field: VerificationField):
    return next(item for item in result.findings if item.field == field)


def all_entries() -> list[tuple[VerificationField, str]]:
    return [
        (VerificationField.BRAND_NAME, "STONE'S   THROW"),
        (VerificationField.CLASS_TYPE_DESIGNATION, "kentucky straight bourbon whiskey"),
        (VerificationField.ALCOHOL_CONTENT, "45% Alc./Vol. (90 Proof)"),
        (VerificationField.NET_CONTENTS, "750 mL"),
        (VerificationField.RESPONSIBLE_PARTY_NAME, "Example Distilling Company"),
        (VerificationField.RESPONSIBLE_PARTY_ADDRESS, "Frankfort, KY, USA"),
        (VerificationField.GOVERNMENT_WARNING_TEXT, GOVERNMENT_WARNING_TEXT),
        (VerificationField.GOVERNMENT_WARNING_HEADING_CASE, "GOVERNMENT WARNING:"),
    ]


def test_clear_label_matches_all_applicable_requirements() -> None:
    result = compare(comparison_input(all_entries()))

    assert result.overall_status == OverallReviewStatus.NO_DISCREPANCIES_FOUND
    assert finding(result, VerificationField.BRAND_NAME).outcome == VerificationOutcome.MATCH
    assert finding(result, VerificationField.NET_CONTENTS).outcome == VerificationOutcome.MATCH
    assert (
        finding(result, VerificationField.COUNTRY_OF_ORIGIN).outcome
        == VerificationOutcome.NOT_APPLICABLE
    )
    assert all(
        item.field != VerificationField.GOVERNMENT_WARNING_HEADING_WEIGHT
        for item in result.findings
    )


def test_punctuation_only_name_difference_requires_review() -> None:
    entries = all_entries()
    entries[0] = (VerificationField.BRAND_NAME, "Stones Throw")

    result = compare(comparison_input(entries))

    assert (
        finding(result, VerificationField.BRAND_NAME).outcome == VerificationOutcome.POSSIBLE_MATCH
    )
    assert result.overall_status == OverallReviewStatus.REVIEW_NEEDED


def test_numeric_difference_is_a_mismatch() -> None:
    entries = all_entries()
    entries[2] = (VerificationField.ALCOHOL_CONTENT, "44% Alc./Vol. (88 Proof)")

    result = compare(comparison_input(entries))

    assert (
        finding(result, VerificationField.ALCOHOL_CONTENT).outcome == VerificationOutcome.MISMATCH
    )


def test_warning_change_is_a_mismatch_but_incomplete_warning_needs_review() -> None:
    entries = all_entries()
    entries[6] = (
        VerificationField.GOVERNMENT_WARNING_TEXT,
        GOVERNMENT_WARNING_TEXT.replace("HEALTH", "SERIOUS HEALTH"),
    )
    assert (
        finding(
            compare(comparison_input(entries)), VerificationField.GOVERNMENT_WARNING_TEXT
        ).outcome
        == VerificationOutcome.MISMATCH
    )

    issue = ExtractionIssue(
        code=ExtractionIssueCode.WARNING_TEXT_INCOMPLETE,
        message="Incomplete",
        image_id="image-1",
        field=VerificationField.GOVERNMENT_WARNING_TEXT,
    )
    assert (
        finding(
            compare(comparison_input(all_entries(), issues=[issue])),
            VerificationField.GOVERNMENT_WARNING_TEXT,
        ).outcome
        == VerificationOutcome.UNABLE_TO_EVALUATE
    )


def test_import_country_matches_alpha_three_representation() -> None:
    entries = all_entries() + [(VerificationField.COUNTRY_OF_ORIGIN, "Product of GBR")]

    result = compare(comparison_input(entries, imported=True))

    assert finding(result, VerificationField.COUNTRY_OF_ORIGIN).outcome == VerificationOutcome.MATCH


def test_conflicting_candidates_require_manual_review() -> None:
    entries = all_entries() + [(VerificationField.BRAND_NAME, "Different Brand")]

    result = compare(comparison_input(entries))

    assert (
        finding(result, VerificationField.BRAND_NAME).outcome
        == VerificationOutcome.UNABLE_TO_EVALUATE
    )
    assert result.overall_status == OverallReviewStatus.ANALYSIS_INCOMPLETE


def test_every_expected_responsible_party_is_compared_independently() -> None:
    base = comparison_input(all_entries())
    name_segment, name_candidate = candidate(
        VerificationField.RESPONSIBLE_PARTY_NAME, "Second Bottling Company", 20
    )
    address_segment, address_candidate = candidate(
        VerificationField.RESPONSIBLE_PARTY_ADDRESS, "Louisville, KY, USA", 21
    )
    second_party = ResponsibleParty(
        name="Second Bottling Company",
        address=PostalAddress(city="Louisville", region="KY", country_code="US"),
    )
    application_with_two_parties = base.application.model_copy(
        update={
            "expected_label": base.application.expected_label.model_copy(
                update={
                    "responsible_parties": [
                        *base.application.expected_label.responsible_parties,
                        second_party,
                    ]
                }
            )
        }
    )
    extraction_with_two_parties = base.extraction.model_copy(
        update={
            "segments": [*base.extraction.segments, name_segment, address_segment],
            "field_candidates": [
                *base.extraction.field_candidates,
                name_candidate,
                address_candidate,
            ],
        }
    )

    result = compare(
        base.model_copy(
            update={
                "application": application_with_two_parties,
                "extraction": extraction_with_two_parties,
            }
        )
    )

    name_findings = [
        item for item in result.findings if item.field == VerificationField.RESPONSIBLE_PARTY_NAME
    ]
    address_findings = [
        item
        for item in result.findings
        if item.field == VerificationField.RESPONSIBLE_PARTY_ADDRESS
    ]
    assert [item.outcome for item in name_findings] == [
        VerificationOutcome.MATCH,
        VerificationOutcome.MATCH,
    ]
    assert [item.outcome for item in address_findings] == [
        VerificationOutcome.MATCH,
        VerificationOutcome.MATCH,
    ]
