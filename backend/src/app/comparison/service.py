"""Deterministic comparison of application values with OCR observations."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from time import perf_counter
from uuid import uuid4

import pycountry

from app.models.extraction import (
    ExtractedFieldCandidate,
    ExtractionIssueCode,
    ExtractionStatus,
    VerificationField,
)
from app.models.label import AlcoholContent, NetContents, ResponsibleParty
from app.models.verification import (
    ComparisonInput,
    ComparisonValue,
    EvidenceReference,
    FindingSeverity,
    OverallReviewStatus,
    VerificationFinding,
    VerificationOutcome,
    VerificationResult,
)
from app.rules import GOVERNMENT_WARNING_TEXT

_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s]", flags=re.UNICODE)
_NON_ALNUM = re.compile(r"[^\w]", flags=re.UNICODE)
_NUMBER = r"(?P<value>\d+(?:\.\d+)?)"
_ABV_PATTERN = re.compile(
    rf"{_NUMBER}\s*(?:%\s*(?:alc(?:ohol)?\.?\s*(?:by\s*)?(?:vol(?:ume)?\.?)?)|%|percent)",
    re.IGNORECASE,
)
_PROOF_PATTERN = re.compile(rf"{_NUMBER}\s*proof\b", re.IGNORECASE)
_NET_PATTERN = re.compile(
    rf"{_NUMBER}\s*(?P<unit>mL|ml|millilit(?:er|re)s?|L|lit(?:er|re)s?|fl\.?\s*oz\.?|fluid\s*ounces?|pints?|pts?\.?|quarts?|qts?\.?|gallons?|gals?\.?)\b",
    re.IGNORECASE,
)
_ML_PER_UNIT = {
    "ml": Decimal("1"),
    "l": Decimal("1000"),
    "fl_oz": Decimal("29.5735295625"),
    "pt": Decimal("473.176473"),
    "qt": Decimal("946.352946"),
    "gal": Decimal("3785.411784"),
}
_UNIT_ALIASES = {
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "l": "l",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "floz": "fl_oz",
    "fluidounce": "fl_oz",
    "fluidounces": "fl_oz",
    "pt": "pt",
    "pts": "pt",
    "pint": "pt",
    "pints": "pt",
    "qt": "qt",
    "qts": "qt",
    "quart": "qt",
    "quarts": "qt",
    "gal": "gal",
    "gals": "gal",
    "gallon": "gal",
    "gallons": "gal",
}
_GLOBAL_INCOMPLETE_ISSUES = {
    ExtractionIssueCode.EXTRACTOR_TIMEOUT,
    ExtractionIssueCode.EXTRACTOR_UNAVAILABLE,
    ExtractionIssueCode.EXTRACTOR_REFUSED,
    ExtractionIssueCode.EXTRACTOR_INVALID_RESPONSE,
    ExtractionIssueCode.NOT_LABEL_IMAGE,
    ExtractionIssueCode.LABEL_CLASSIFICATION_UNCERTAIN,
    ExtractionIssueCode.NO_TEXT_FOUND,
    ExtractionIssueCode.IMAGE_UNREADABLE,
}


def _collapse(value: str) -> str:
    return _WHITESPACE.sub(" ", value.strip())


def _text_key(value: str) -> str:
    return _collapse(unicodedata.normalize("NFKC", value)).casefold()


def _punctuation_key(value: str) -> str:
    return _collapse(_PUNCTUATION.sub("", unicodedata.normalize("NFKC", value))).casefold()


def _component_key(value: str) -> str:
    return _NON_ALNUM.sub("", unicodedata.normalize("NFKC", value)).casefold()


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _unit_key(value: str) -> str | None:
    return _UNIT_ALIASES.get(_NON_ALNUM.sub("", value).casefold())


def _country_identity(value: str) -> str | None:
    clean = _collapse(value)
    aliases = {"usa": "US", "u.s.a.": "US", "u.s.": "US", "uk": "GB", "u.k.": "GB"}
    candidate = aliases.get(clean.casefold(), clean)
    try:
        country = pycountry.countries.lookup(candidate)
    except LookupError:
        return None
    return str(country.alpha_2)


def _severity(outcome: VerificationOutcome) -> FindingSeverity:
    if outcome in {VerificationOutcome.MATCH, VerificationOutcome.NOT_APPLICABLE}:
        return FindingSeverity.INFORMATION
    if outcome in {VerificationOutcome.POSSIBLE_MATCH, VerificationOutcome.UNABLE_TO_EVALUATE}:
        return FindingSeverity.REVIEW
    return FindingSeverity.DISCREPANCY


def _overall(findings: list[VerificationFinding]) -> OverallReviewStatus:
    outcomes = {finding.outcome for finding in findings}
    if VerificationOutcome.UNABLE_TO_EVALUATE in outcomes:
        return OverallReviewStatus.ANALYSIS_INCOMPLETE
    if outcomes & {
        VerificationOutcome.POSSIBLE_MATCH,
        VerificationOutcome.MISMATCH,
        VerificationOutcome.NOT_FOUND,
    }:
        return OverallReviewStatus.REVIEW_NEEDED
    return OverallReviewStatus.NO_DISCREPANCIES_FOUND


class ComparisonService:
    def __init__(self, comparison: ComparisonInput) -> None:
        self.comparison = comparison
        self.candidates: dict[VerificationField, list[ExtractedFieldCandidate]] = defaultdict(list)
        for candidate in comparison.extraction.field_candidates:
            self.candidates[candidate.field].append(candidate)
        self.segments = {segment.segment_id: segment for segment in comparison.extraction.segments}
        self.field_issues: dict[VerificationField, set[ExtractionIssueCode]] = defaultdict(set)
        self.global_incomplete = comparison.extraction.status == ExtractionStatus.FAILED
        for issue in comparison.extraction.issues:
            if issue.field is not None:
                self.field_issues[issue.field].add(issue.code)
            if issue.field is None and issue.code in _GLOBAL_INCOMPLETE_ISSUES:
                self.global_incomplete = True

    def _evidence(self, candidates: list[ExtractedFieldCandidate]) -> list[EvidenceReference]:
        references: list[EvidenceReference] = []
        for candidate in candidates:
            segment_ids = candidate.evidence_segment_ids
            segment = self.segments.get(segment_ids[0])
            if segment is None:
                continue
            references.append(
                EvidenceReference(
                    image_id=segment.image_id,
                    segment_ids=segment_ids,
                    region=segment.region,
                    excerpt=candidate.raw_text,
                )
            )
        return references

    def _finding(
        self,
        field: VerificationField,
        outcome: VerificationOutcome,
        rule_id: str,
        explanation: str,
        expected: ComparisonValue | None,
        candidates: list[ExtractedFieldCandidate] | None = None,
    ) -> VerificationFinding:
        candidates = candidates or []
        return VerificationFinding(
            field=field,
            outcome=outcome,
            severity=_severity(outcome),
            rule_id=rule_id,
            explanation=explanation,
            expected=expected,
            detected=[
                ComparisonValue(display_value=candidate.raw_text) for candidate in candidates
            ],
            evidence=self._evidence(candidates),
        )

    def _availability(
        self, field: VerificationField, candidates: list[ExtractedFieldCandidate]
    ) -> VerificationOutcome | None:
        if self.global_incomplete or self.field_issues[field]:
            return VerificationOutcome.UNABLE_TO_EVALUATE
        if not candidates:
            return VerificationOutcome.NOT_FOUND
        keys = {_text_key(candidate.raw_text) for candidate in candidates}
        if len(keys) > 1:
            return VerificationOutcome.UNABLE_TO_EVALUATE
        return None

    def _text_finding(
        self, field: VerificationField, expected_text: str, rule_id: str
    ) -> VerificationFinding:
        candidates = self.candidates[field]
        expected = ComparisonValue(
            display_value=expected_text, normalized_value=_text_key(expected_text)
        )
        available = self._availability(field, candidates)
        if available is not None:
            explanation = (
                "Reliable label evidence is unavailable."
                if available == VerificationOutcome.UNABLE_TO_EVALUATE
                else "This required value was not found on the label."
            )
            return self._finding(field, available, rule_id, explanation, expected, candidates)
        detected = candidates[0].raw_text
        if _text_key(detected) == _text_key(expected_text):
            return self._finding(
                field,
                VerificationOutcome.MATCH,
                rule_id,
                "The label text matches after case and whitespace normalization.",
                expected,
                candidates,
            )
        if _punctuation_key(detected) == _punctuation_key(expected_text):
            return self._finding(
                field,
                VerificationOutcome.POSSIBLE_MATCH,
                rule_id,
                "The text differs only by punctuation and needs review.",
                expected,
                candidates,
            )
        return self._finding(
            field,
            VerificationOutcome.MISMATCH,
            rule_id,
            "The detected label text differs from the expected value.",
            expected,
            candidates,
        )

    def _alcohol(self, expected_content: AlcoholContent | None) -> VerificationFinding:
        field = VerificationField.ALCOHOL_CONTENT
        rule_id = "alcohol-content-v1"
        if expected_content is None:
            return self._finding(
                field,
                VerificationOutcome.NOT_APPLICABLE,
                rule_id,
                "Alcohol content is not expected for this product.",
                None,
            )
        candidates = self.candidates[field]
        expected = ComparisonValue(
            display_value=expected_content.expected_display_text
            or f"{expected_content.abv_percent}% ABV",
            normalized_value=str(expected_content.abv_percent),
            unit="ABV percent",
        )
        available = self._availability(field, candidates)
        if available is not None:
            return self._finding(
                field,
                available,
                rule_id,
                "Reliable alcohol-content evidence is unavailable."
                if available == VerificationOutcome.UNABLE_TO_EVALUATE
                else "Alcohol content was not found on the label.",
                expected,
                candidates,
            )
        text = candidates[0].raw_text
        abv_values = {_decimal(match.group("value")) for match in _ABV_PATTERN.finditer(text)}
        proof_values = {_decimal(match.group("value")) for match in _PROOF_PATTERN.finditer(text)}
        abv_values.discard(None)
        proof_values.discard(None)
        expected_abv = Decimal(str(expected_content.abv_percent))
        expected_proof = (
            Decimal(str(expected_content.proof)) if expected_content.proof is not None else None
        )
        observed_abv = abv_values | {proof / Decimal("2") for proof in proof_values}
        observed_proof = proof_values | {abv * Decimal("2") for abv in abv_values}
        if (
            not observed_abv
            or expected_abv not in observed_abv
            or (expected_proof is not None and expected_proof not in observed_proof)
        ):
            return self._finding(
                field,
                VerificationOutcome.MISMATCH,
                rule_id,
                "A detected alcohol-content number does not match the expected value.",
                expected,
                candidates,
            )
        return self._finding(
            field,
            VerificationOutcome.MATCH,
            rule_id,
            "All supplied ABV and proof values match exactly.",
            expected,
            candidates,
        )

    def _net_contents(self, expected_contents: NetContents) -> VerificationFinding:
        field = VerificationField.NET_CONTENTS
        rule_id = "net-contents-v1"
        candidates = self.candidates[field]
        expected_unit = _unit_key(expected_contents.unit.value)
        assert expected_unit is not None
        expected_ml = Decimal(str(expected_contents.value)) * _ML_PER_UNIT[expected_unit]
        expected = ComparisonValue(
            display_value=expected_contents.expected_display_text
            or f"{expected_contents.value} {expected_contents.unit.value}",
            normalized_value=str(expected_ml),
            unit="mL",
        )
        available = self._availability(field, candidates)
        if available is not None:
            return self._finding(
                field,
                available,
                rule_id,
                "Reliable net-contents evidence is unavailable."
                if available == VerificationOutcome.UNABLE_TO_EVALUATE
                else "Net contents were not found on the label.",
                expected,
                candidates,
            )
        measurements: set[Decimal] = set()
        for match in _NET_PATTERN.finditer(candidates[0].raw_text):
            value, unit = _decimal(match.group("value")), _unit_key(match.group("unit"))
            if value is not None and unit is not None:
                measurements.add(value * _ML_PER_UNIT[unit])
        if expected_ml not in measurements:
            return self._finding(
                field,
                VerificationOutcome.MISMATCH,
                rule_id,
                "The detected net-contents number does not match after unit conversion.",
                expected,
                candidates,
            )
        return self._finding(
            field,
            VerificationOutcome.MATCH,
            rule_id,
            "Net contents match exactly after unit conversion.",
            expected,
            candidates,
        )

    def _party_findings(self, party: ResponsibleParty, index: int) -> list[VerificationFinding]:
        name_field = VerificationField.RESPONSIBLE_PARTY_NAME
        name_candidates = self.candidates[name_field]
        name_rule_id = f"responsible-party-name-{index + 1}-v1"
        name_expected = ComparisonValue(
            display_value=party.name,
            normalized_value=_text_key(party.name),
        )
        if self.global_incomplete or self.field_issues[name_field]:
            name = self._finding(
                name_field,
                VerificationOutcome.UNABLE_TO_EVALUATE,
                name_rule_id,
                "Reliable business-name evidence is unavailable.",
                name_expected,
                name_candidates,
            )
        elif not name_candidates:
            name = self._finding(
                name_field,
                VerificationOutcome.NOT_FOUND,
                name_rule_id,
                "The expected business name was not found on the label.",
                name_expected,
            )
        elif any(
            _text_key(candidate.raw_text) == _text_key(party.name) for candidate in name_candidates
        ):
            name = self._finding(
                name_field,
                VerificationOutcome.MATCH,
                name_rule_id,
                "The business name matches after case and whitespace normalization.",
                name_expected,
                name_candidates,
            )
        elif any(
            _punctuation_key(candidate.raw_text) == _punctuation_key(party.name)
            for candidate in name_candidates
        ):
            name = self._finding(
                name_field,
                VerificationOutcome.POSSIBLE_MATCH,
                name_rule_id,
                "The business name differs only by punctuation and needs review.",
                name_expected,
                name_candidates,
            )
        else:
            name = self._finding(
                name_field,
                VerificationOutcome.MISMATCH,
                name_rule_id,
                "No detected business name matches this expected party.",
                name_expected,
                name_candidates,
            )
        field = VerificationField.RESPONSIBLE_PARTY_ADDRESS
        candidates = self.candidates[field]
        components = [
            *party.address.street_lines,
            party.address.city,
            party.address.region,
            party.address.postal_code,
        ]
        components = [component for component in components if component]
        expected_text = ", ".join([*components, party.address.country_code])
        expected = ComparisonValue(
            display_value=expected_text,
            normalized_value=" | ".join(_component_key(component) for component in components),
            unit=party.address.country_code,
        )
        rule_id = f"responsible-party-address-{index + 1}-v1"
        if self.global_incomplete or self.field_issues[field]:
            return [
                name,
                self._finding(
                    field,
                    VerificationOutcome.UNABLE_TO_EVALUATE,
                    rule_id,
                    "Reliable address evidence is unavailable.",
                    expected,
                    candidates,
                ),
            ]
        if not candidates:
            return [
                name,
                self._finding(
                    field,
                    VerificationOutcome.NOT_FOUND,
                    rule_id,
                    "The expected address was not found on the label.",
                    expected,
                ),
            ]
        expected_country = _country_identity(party.address.country_code)

        def address_matches(candidate: ExtractedFieldCandidate) -> bool:
            country_matches = expected_country is not None and expected_country in {
                _country_identity(token) for token in re.findall(r"[A-Za-z.]+", candidate.raw_text)
            }
            if not country_matches and expected_country is not None:
                country_matches = expected_country == _country_identity(candidate.raw_text)
            return (
                all(
                    _component_key(component) in _component_key(candidate.raw_text)
                    for component in components
                )
                and country_matches
            )

        if any(address_matches(candidate) for candidate in candidates):
            address = self._finding(
                field,
                VerificationOutcome.MATCH,
                rule_id,
                "All populated address components appear on the label.",
                expected,
                candidates,
            )
        else:
            address = self._finding(
                field,
                VerificationOutcome.MISMATCH,
                rule_id,
                "One or more expected address components are absent from the label.",
                expected,
                candidates,
            )
        return [name, address]

    def _country_of_origin(self) -> VerificationFinding:
        field = VerificationField.COUNTRY_OF_ORIGIN
        rule_id = "country-of-origin-v1"
        application = self.comparison.application
        if not application.imported or application.expected_label.country_of_origin is None:
            return self._finding(
                field,
                VerificationOutcome.NOT_APPLICABLE,
                rule_id,
                "Country of origin is not required for this non-imported product.",
                None,
            )
        origin = application.expected_label.country_of_origin
        candidates = self.candidates[field]
        expected = ComparisonValue(
            display_value=origin.display_name,
            normalized_value=origin.country_code,
            unit=origin.country_code,
        )
        available = self._availability(field, candidates)
        if available is not None:
            return self._finding(
                field,
                available,
                rule_id,
                "Reliable country-of-origin evidence is unavailable."
                if available == VerificationOutcome.UNABLE_TO_EVALUATE
                else "Country of origin was not found on the label.",
                expected,
                candidates,
            )
        detected_identity = _country_identity(candidates[0].raw_text)
        if detected_identity is None:
            for token in re.findall(r"[A-Za-z.]+", candidates[0].raw_text):
                detected_identity = _country_identity(token)
                if detected_identity is not None:
                    break
        if detected_identity == origin.country_code:
            return self._finding(
                field,
                VerificationOutcome.MATCH,
                rule_id,
                "Country-of-origin representations identify the same country.",
                expected,
                candidates,
            )
        return self._finding(
            field,
            VerificationOutcome.MISMATCH,
            rule_id,
            "The detected country of origin differs from the expected country.",
            expected,
            candidates,
        )

    def _warning(self) -> list[VerificationFinding]:
        text = self._warning_text()
        heading_case = self._heading_case()
        return [text, heading_case]

    def _warning_text(self) -> VerificationFinding:
        field = VerificationField.GOVERNMENT_WARNING_TEXT
        candidates = self.candidates[field]
        expected = ComparisonValue(display_value=GOVERNMENT_WARNING_TEXT)
        rule_id = "government-warning-text-v1"
        if ExtractionIssueCode.WARNING_TEXT_INCOMPLETE in self.field_issues[field]:
            return self._finding(
                field,
                VerificationOutcome.UNABLE_TO_EVALUATE,
                rule_id,
                "The warning text is incomplete or unclear and requires review.",
                expected,
                candidates,
            )
        available = self._availability(field, candidates)
        if available is not None:
            return self._finding(
                field,
                available,
                rule_id,
                "Reliable warning-text evidence is unavailable."
                if available == VerificationOutcome.UNABLE_TO_EVALUATE
                else "The government warning was not found on the label.",
                expected,
                candidates,
            )
        if _collapse(candidates[0].raw_text) == _collapse(GOVERNMENT_WARNING_TEXT):
            return self._finding(
                field,
                VerificationOutcome.MATCH,
                rule_id,
                "The warning matches the approved reference after whitespace normalization only.",
                expected,
                candidates,
            )
        return self._finding(
            field,
            VerificationOutcome.MISMATCH,
            rule_id,
            "The warning differs from the approved reference.",
            expected,
            candidates,
        )

    def _heading_case(self) -> VerificationFinding:
        field = VerificationField.GOVERNMENT_WARNING_HEADING_CASE
        candidates = self.candidates[field]
        expected = ComparisonValue(
            display_value="GOVERNMENT WARNING:", normalized_value="uppercase"
        )
        available = self._availability(field, candidates)
        if available is not None:
            return self._finding(
                field,
                available,
                "government-warning-heading-case-v1",
                "Reliable heading-case evidence is unavailable."
                if available == VerificationOutcome.UNABLE_TO_EVALUATE
                else "The warning heading was not found on the label.",
                expected,
                candidates,
            )
        if candidates[0].normalized_value == "uppercase":
            return self._finding(
                field,
                VerificationOutcome.MATCH,
                "government-warning-heading-case-v1",
                "The warning heading is uppercase.",
                expected,
                candidates,
            )
        return self._finding(
            field,
            VerificationOutcome.MISMATCH,
            "government-warning-heading-case-v1",
            "The warning heading is not uppercase.",
            expected,
            candidates,
        )

    def evaluate(self) -> list[VerificationFinding]:
        label = self.comparison.application.expected_label
        findings = [
            self._text_finding(VerificationField.BRAND_NAME, label.brand_name, "brand-name-v1"),
            self._text_finding(
                VerificationField.CLASS_TYPE_DESIGNATION,
                label.class_type_designation,
                "class-type-designation-v1",
            ),
            self._alcohol(label.alcohol_content),
            self._net_contents(label.net_contents),
        ]
        for index, party in enumerate(label.responsible_parties):
            findings.extend(self._party_findings(party, index))
        findings.append(self._country_of_origin())
        findings.extend(self._warning())
        return findings


def compare(comparison: ComparisonInput) -> VerificationResult:
    started_at = datetime.now(UTC)
    timer = perf_counter()
    findings = ComparisonService(comparison).evaluate()
    completed_at = datetime.now(UTC)
    return VerificationResult(
        verification_id=f"verification-{uuid4()}",
        submission_id=comparison.extraction.submission_id,
        record_id=comparison.application.record_id,
        overall_status=_overall(findings),
        ruleset=comparison.ruleset,
        extractor=comparison.extraction.extractor,
        findings=findings,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=round((perf_counter() - timer) * 1000),
    )
