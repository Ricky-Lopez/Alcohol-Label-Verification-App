# Alcohol Label Verification Prototype Data Model

## 1. Purpose and authority

This document defines the data passed from frontend intake through OCR extraction and deterministic
comparison to the agent-facing verification result. The canonical executable definitions are the
Pydantic models under `backend/src/app/models/`.

The generated artifacts are:

- `contracts/verification.schema.json` for the language-neutral boundary contract; and
- `frontend/src/api/generated/verification.ts` for browser compile-time types.

The model supports compliance decision assistance. It does not encode a final regulatory decision
and cannot replace an agent or an approved, versioned ruleset.

## 2. Data flow

```text
Frontend form and image files
          │
          ▼
VerificationSubmission ───────────────┐
          │                           │
          ▼                           │
Validated image bytes                 │ expected application values
          │                           │
          ▼                           │
OCR adapter                           │
          │                           │
          ▼                           ▼
OcrExtractionResult ──────────► ComparisonInput
                                       │
                                       ▼
                              deterministic rules
                                       │
                                       ▼
                              VerificationResult
                                       │
                                       ▼
                              agent review interface
```

Image bytes travel as multipart file parts. They are not embedded in JSON, the generated schema, or
logs. `LabelImageInput` contains only metadata and a client-scoped identifier used to associate a
file with OCR evidence.

## 3. Contract conventions

- JSON uses `camelCase`; Python uses `snake_case` internally.
- Contract objects reject unknown fields rather than silently ignoring input.
- `schemaVersion` supports controlled future evolution.
- Correlation identifiers connect a submission, application record, image, OCR segment, extraction,
  and verification.
- OCR coordinates are normalized from `0` to `1` so evidence remains valid across display sizes.
- Confidence is constrained from `0` to `1` and is never a substitute for evidence.
- The contract uses safe status and issue codes; it does not require exception text or provider
  responses to cross service boundaries.
- Prototype records and images must remain public or synthetic.

## 4. Frontend submission model

### 4.1 Frontend relationship tree

The frontend begins with a `VerificationSubmission`. This is the root JSON object sent by the
browser to start verification. Its objects are nested as follows:

<pre><strong><em><u>VerificationSubmission</u></em></strong>
├── submissionId
├── application: <strong><em><u>ApplicationRecord</u></em></strong>
│   ├── recordId
│   ├── intakeSource
│   ├── beverageType
│   ├── imported
│   └── expectedLabel: <strong><em><u>ExpectedLabelFields</u></em></strong>
│       ├── brandName
│       ├── classTypeDesignation
│       ├── alcoholContent: AlcoholContent | null
│       ├── netContents: NetContents
│       ├── responsibleParties: ResponsibleParty[]
│       ├── countryOfOrigin: CountryOfOrigin | null
│       ├── appellationOfOrigin: string | null
│       └── additionalRequiredStatements: ExpectedStatement[]
└── images: <strong><em><u>LabelImageInput[]</u></em></strong>
    ├── clientImageId
    ├── fileName
    ├── mediaType
    ├── sizeBytes
    ├── panelType
    └── sha256 (optional)</pre>

The two principal branches have different meanings:

- `application.expectedLabel` describes what is expected to appear on the label.
- `images` describes the label photographs that will be inspected.

`LabelImageInput` contains image metadata only. While the user is selecting files, the browser will
also need temporary UI state that pairs each metadata object with its actual browser `File`:

```ts
// Illustrative frontend-only view model; it is not part of the API contract.
interface PendingLabelImage {
  metadata: LabelImageInput;
  file: File;
}
```

At submission time, the frontend sends the `VerificationSubmission` as JSON and sends the paired
`File` objects as binary parts of the same multipart request. `clientImageId` links each metadata
record to its uploaded file and, later, to OCR evidence from that image.

### 4.2 Frontend lifecycle

The frontend creates only the submission-side data. OCR and comparison outputs are created by the
backend and then returned for the frontend to display:

```text
User selects or enters expected application data
                         │
                         ▼
                  ApplicationRecord
                         +
User selects image files ──► PendingLabelImage[] (frontend-only state)
                         │
                         ▼
              VerificationSubmission + binary files
                         │  sent to backend
                         ▼
                 OcrExtractionResult
                         │  created by OCR adapter
                         ▼
                   ComparisonInput
                         │  assembled and evaluated by backend
                         ▼
                 VerificationResult
                         │  returned to frontend
                         ▼
                Human review interface
```

| Stage | Object | Created by | Frontend responsibility |
| --- | --- | --- | --- |
| Expected data | `ApplicationRecord` | Frontend selection/form or preloaded source | Collect or select values expected on the label |
| Image selection | `PendingLabelImage[]` | Frontend only | Hold each browser `File` beside its `LabelImageInput` metadata |
| Submission | `VerificationSubmission` | Frontend | Validate and send application data plus image metadata and files |
| OCR output | `OcrExtractionResult` | Backend OCR adapter | Display processing state or extracted evidence when needed |
| Comparison | `ComparisonInput` | Backend | No normal construction responsibility; type is available for contract visibility |
| Review result | `VerificationResult` | Backend comparison engine | Present the summary, findings, expected/detected values, and evidence |

In short, the three most important objects have distinct roles:

```text
ApplicationRecord   = what should be on the label
OcrExtractionResult = what the system observed on the uploaded images
VerificationResult  = how the expected and observed values compare
HumanReviewReceipt  = the temporary human approval or rejection recorded for a queued item
```

### 4.3 `VerificationSubmission`

The root frontend input contains:

| Field | Purpose |
| --- | --- |
| `submissionId` | Correlates the upload, extraction, comparison, and result |
| `application` | Structured values expected from the application record |
| `images` | Metadata for one or more multipart image files |

The prototype can populate `application` from a preloaded synthetic record, an ad hoc form, or a P1
batch manifest. These sources share the same contract and are identified by `intakeSource`.

### 4.4 `ApplicationRecord`

| Field | Required | Notes |
| --- | --- | --- |
| `recordId` | Yes | Synthetic application identifier |
| `intakeSource` | Yes | `preloaded`, `ad_hoc`, or `batch` |
| `beverageType` | Yes | `beer`, `wine`, or `distilled_spirits` |
| `imported` | Yes | Drives origin and responsible-party rules |
| `expectedLabel` | Yes | Expected structured label values |

An imported record must include `countryOfOrigin`. A distilled-spirits record must include
`alcoholContent`. Beer and wine retain a nullable alcohol-content field because applicability and
exceptions must be decided by an approved beverage-specific ruleset rather than assumed by the data
contract.

### 4.5 `ExpectedLabelFields`

The model accommodates the common and conditional label information identified in the project brief
and current TTB labeling overviews:

| Label item | Representation | Requirement behavior |
| --- | --- | --- |
| Brand name | `brandName` | Required in every application record |
| Class/type designation | `classTypeDesignation` | Required in every application record |
| Alcohol content | `alcoholContent.abvPercent`, optional proof and display text | Required for distilled spirits; applicability for beer/wine is ruleset-driven |
| Net contents | Numeric `value`, controlled `unit`, optional display text | Required in every application record |
| Bottler/producer identity | One or more `responsibleParties` | Each contains name, address, and an optional statement prefix |
| Country of origin | `countryOfOrigin` | Required when `imported` is true |
| Wine appellation | `appellationOfOrigin` | Available for wine rules that require it |
| Conditional disclosures | `additionalRequiredStatements` | Typed statement category, expected text, and optional rule reference |
| Government health warning | Versioned `RulesetReference`, not user-entered text | Exact expected wording and presentation rules come from the approved ruleset |

`additionalRequiredStatements` accommodates sulfite, color-additive, aspartame, age,
statement-of-composition, foreign-wine-percentage, and other approved conditional statements without
pretending they apply to every product.

TTB currently identifies brand, class/type, alcohol content, health warning, name/address, net
contents, and import origin among mandatory or conditionally mandatory distilled-spirits label
information. Malt-beverage guidance makes alcohol content conditional in some circumstances. Wine
guidance additionally identifies appellation, foreign-wine percentage, sulfite, and other conditional
information. The data model can carry these values, but the ruleset determines whether each is
required for a specific record.

### 4.6 `LabelImageInput`

The image declaration contains `clientImageId`, filename, MIME type, byte size, panel type, and an
optional SHA-256 digest. P0 accepts JPEG and PNG up to the contract maximum of 20 MB per file. The
digest is provenance metadata, not an authentication mechanism.

`panelType` distinguishes brand, back, side, neck, other, and unknown views. This supports evidence
display and future same-field-of-vision checks without assuming that one image contains the complete
container labeling.

## 5. OCR boundary model

### 5.1 OCR relationship tree

The OCR adapter creates an `OcrExtractionResult` after analyzing the uploaded image files. Its
objects are nested as follows:

<pre><strong><em><u>OcrExtractionResult</u></em></strong>
├── extractionId
├── submissionId ──► VerificationSubmission.submissionId
├── status
├── extractor: <strong><em><u>ExtractorReference</u></em></strong>
│   ├── name
│   ├── version
│   └── modelVersion (optional)
├── durationMs
├── timing: <strong><em><u>ExtractionTiming</u></em></strong>
│   ├── imagePreparationMs
│   └── providerMs
├── segments: <strong><em><u>TextSegment[]</u></em></strong>
│   ├── segmentId
│   ├── imageId ──► LabelImageInput.clientImageId
│   ├── rawText
│   ├── confidence (optional)
│   ├── region: <strong><em><u>BoundingPolygon</u></em></strong> (optional)
│   │   └── points: <strong><em><u>Point[]</u></em></strong>
│   │       ├── x
│   │       └── y
│   └── orientationDegrees (optional)
├── fieldCandidates: <strong><em><u>ExtractedFieldCandidate[]</u></em></strong>
│   ├── field
│   ├── rawText
│   ├── normalizedValue (optional)
│   ├── confidence (optional)
│   └── evidenceSegmentIds[] ──► TextSegment.segmentId
└── issues: <strong><em><u>ExtractionIssue[]</u></em></strong>
    ├── code
    ├── message
    ├── imageId (optional) ──► LabelImageInput.clientImageId
    └── field (optional)</pre>

The identifiers draw the important lines between otherwise separate objects:

- `submissionId` connects the OCR output to the original `VerificationSubmission`.
- `TextSegment.imageId` connects recognized text to the `LabelImageInput` describing its source
  image.
- `ExtractedFieldCandidate.evidenceSegmentIds` connects an interpreted field, such as alcohol
  content, to the exact `TextSegment` objects supporting it.
- `ExtractionIssue.imageId` identifies the affected image when an OCR problem is image-specific.

For example, OCR may create a `TextSegment` containing `45% ALC./VOL.` and then create an
`ExtractedFieldCandidate` for `alcohol_content` that references that segment. This preserves both
the interpreted value used for comparison and the original image evidence shown to the reviewer.

### 5.2 `OcrExtractionResult`

The OCR adapter returns engine-neutral data:

- extraction and submission identifiers;
- `succeeded`, `partial`, or `failed` status;
- extractor, software version, and optional model version;
- total server analysis duration, plus image-preparation and provider timing;
- raw text segments with confidence and normalized polygons;
- field candidates that point to their supporting segment identifiers; and
- safe issue codes for low confidence, unreadable images, unsupported layouts, timeout, or provider
  unavailability.

OpenAI vision does not supply calibrated OCR confidence or guaranteed bounding geometry. Those
properties are therefore nullable and must never be fabricated. The compact provider-specific
response returns each field observation once. The adapter creates a matching text segment and
candidate, then assigns their public evidence identifiers. This avoids asking the model to repeat
the same text in both provider segments and candidates.

Government-warning candidates preserve the visible wording in `rawText` and leave
`normalizedValue` null. OCR is instructed not to correct, complete, paraphrase, or normalize the
warning. Exact comparison against the approved, versioned reference remains deterministic
comparison-engine work.

Each image is classified as an alcohol label, a non-label image, or uncertain. Non-label images
produce `not_label_image` rather than field candidates; uncertain and incomplete warning evidence
produce reviewable issues. Provider timeouts, refusals, and invalid structured responses use safe,
typed issue codes without exposing provider response content.

Candidate fields include all core and anticipated checks: brand, class/type, alcohol content, net
contents, responsible-party information, origin, appellation, warning text and presentation,
same-field-of-vision, general legibility, and additional required statements.

The model rejects a field candidate that references an unknown text segment. A failed extraction
cannot claim extracted field candidates.

## 6. Comparison-engine input

`ComparisonInput` combines:

- the structured application values;
- validated image metadata;
- the OCR result; and
- the exact `RulesetReference` used for comparison.

The model rejects OCR segments associated with images outside the comparison. This prevents evidence
from one application from being attached accidentally to another.

The comparison engine uses deterministic normalization and comparison code. AI/OCR proposes
detected text and regions; it does not decide whether a regulatory requirement passes. The prototype
compares all seven label requirements: brand, class/type, applicable alcohol content, net contents,
bottler/producer name and address, imported-product origin, and the versioned government warning.
Case and whitespace-only name differences match; punctuation-only name differences require review;
numeric values must match exactly after approved conversion.

## 7. Verification result model

### 7.1 `VerificationFinding`

Each field-level finding contains:

| Field | Purpose |
| --- | --- |
| `field` | The label element or presentation rule being evaluated |
| `outcome` | `match`, `possible_match`, `mismatch`, `not_found`, `not_applicable`, or `unable_to_evaluate` |
| `severity` | `information`, `review`, or `discrepancy` |
| `ruleId` | Stable identifier for the applied deterministic rule |
| `explanation` | Plain-language reason shown to the agent |
| `expected` | Expected application or ruleset value, when applicable |
| `detected` | One or more values detected on the label |
| `confidence` | Optional extraction confidence from `0` to `1` |
| `evidence` | Image, text-segment, region, and optional excerpt references |

Keeping `expected` and `detected` separate preserves original evidence when normalization determines
that capitalization or whitespace differences are harmless.

### 7.2 `VerificationResult`

The final decision-support response contains record correlation, overall review status, the ruleset
and extractor versions, all field findings, timezone-aware timestamps, and measured duration.

`decisionSupportOnly` is always `true`. Overall statuses are deliberately non-regulatory:

- `no_discrepancies_found`
- `review_needed`
- `analysis_incomplete`

The model prevents `no_discrepancies_found` from containing a mismatch, possible match, missing field,
or unable-to-evaluate finding.

## 8. Regulatory and scope boundaries

The contract can represent generally required and conditional label data, but it is not itself a
complete regulatory rules engine. In particular:

- exact health-warning text, heading capitalization, boldness, type size, prominence, and placement
  belong to a dated ruleset;
- distilled-spirits same-field-of-vision requirements need multi-region image evidence;
- alcohol-content applicability differs among beverage categories and circumstances;
- wine appellation and disclosure requirements are conditional;
- responsible-party wording and address requirements depend on the applicable product and import status; and
- future rules must be introduced through versioned rule and schema changes with regression tests.

Reference material used to establish field coverage:

- [TTB distilled spirits labeling overview](https://www.ttb.gov/regulated-commodities/beverage-alcohol/distilled-spirits/labeling)
- [TTB malt beverage mandatory label information](https://www.ttb.gov/regulated-commodities/beverage-alcohol/beer/labeling/malt-beverage-mandatory-label-information)
- [TTB wine labeling overview](https://www.ttb.gov/labeling-wine/ttb-wine-labeling-home)
- [TTB distilled spirits label anatomy](https://www.ttb.gov/regulated-commodities/beverage-alcohol/distilled-spirits/ds-labeling-home/anatomy-of-a-distilled-spirits-label-tool)

Product owners must approve the dated ruleset before the prototype represents any check as complete.

## 9. Contract evolution

To change a boundary type:

1. Update the Pydantic model and add or revise validation tests.
2. Run `uv run python scripts/export_contract.py` from `backend/`.
3. Run `npm run generate:contracts` from `frontend/`.
4. Review both generated diffs.
5. Run backend tests, Ruff, frontend tests, TypeScript checking, and the production build.
6. Increment `schemaVersion` for a breaking contract change.

Generated files must not be edited by hand.
