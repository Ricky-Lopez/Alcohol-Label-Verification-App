# Alcohol Label Verification Web Application Requirements

## 1. Document purpose

This document translates the stakeholder interviews and project brief in
`docs/INSTRUCTIONS.md` into prioritized, testable requirements for a web application prototype.
It is intended to guide design, implementation, testing, and stakeholder acceptance.

The prototype is a decision-support tool. It assists a compliance agent by extracting label
information, comparing it with application data, and presenting evidence for review. It must not
represent its output as a final regulatory determination or automatically approve or reject an
application.

## 2. Priority definitions

- **P0 — Required for the prototype:** The application is not acceptable without this capability.
- **P1 — Operationally important:** Not a blocker for demonstrating the time-constrained core, but
  the next priority after P0 because it addresses a stated operational need.
- **P2 — Stretch goal:** Valuable enhancement that must not put the working core at risk.
- **Future production requirement:** Not required for the prototype, but must be addressed before
  use with real applications or controlled data.

## 3. Product goals and success measures

The prototype must demonstrate that routine alcohol-label checks can be made faster and easier
without removing agent judgment.

| ID | Goal | Success measure |
| --- | --- | --- |
| G-01 | Reduce routine visual comparison work | A user can open or supply an application record, attach its label, and review field-level results without retyping data that the system already has. |
| G-02 | Return useful results quickly | A supported single-label request returns usable verification results within about 5 seconds under the documented demo conditions. Failures are measured separately and do not count as successful responses. |
| G-03 | Preserve human judgment | Every result includes evidence and can be reviewed by an agent; the system never makes an irreversible approval or rejection decision. |
| G-04 | Be usable across a wide range of technical comfort | Primary actions and outcomes are visible, plainly worded, keyboard accessible, and do not require training or hidden navigation. |
| G-05 | Demonstrate a complete, testable prototype | Reviewers receive source code, setup documentation, documented assumptions and limitations, and an accessible deployed application URL. |

## 4. Scope, users, and input model

### 4.1 Application scope

The application is a standalone proof of concept for assisted alcohol-label review. It receives
expected values from an application record, extracts values and visual evidence from associated
label artwork, compares the two, and presents discrepancies or uncertainty to a human agent.

The core prototype covers the three checks repeatedly identified in the interviews:

1. Brand-name comparison with transparent normalization and human judgment.
2. Alcohol-content comparison, including explicit beverage-specific applicability.
3. Government-warning verification for exact wording, uppercase heading, and bold-heading evidence.

The prototype may extract and display other label fields, but full regulatory validation of every
field, beverage variation, type-size rule, or placement rule is not part of the time-constrained
core unless an authoritative rule and acceptance example have first been approved.

### 4.2 Expected users and demographics

The primary user is a compliance agent reviewing an alcohol label against values supplied in a
label application. Agents vary substantially in technical comfort and may be processing labels
under significant queue pressure.

The source material describes a team of 47 agents handling approximately 150,000 applications per
year. Half of the team is over 50. Tenure ranges from a junior agent with eight months of experience
to a senior agent with 28 years of experience. Technical confidence ranges from highly comfortable
with software to users who avoid unfamiliar digital workflows. These are the supported demographic
facts; the transcript does not establish users' gender distribution, disability status, language
needs, device ownership, or other demographic characteristics.

The design must therefore support experienced and junior agents alike, avoid age-based assumptions,
and favor visible actions, plain language, familiar checklist structure, keyboard access, readable
type, and forgiving recovery from errors. Accessibility is a product requirement, not an inference
that age itself implies disability.

Secondary users and stakeholders are:

- Compliance managers, who care about throughput, consistency, exception visibility, and adoption.
- IT and security staff, who care about deployment boundaries, blocked outbound traffic, data
  handling, supportability, and any future federal authorization.
- Prototype evaluators and future procurement stakeholders, who need synthetic sample data, clear
  limitations, reproducible setup, and measurable evidence that the concept works.

Applicants, importers, and members of the public are data originators or affected parties, not
direct users of this prototype. No applicant-facing submission portal is requested.

### 4.3 Input sources and collection

Two inputs are needed for a comparison:

1. **Expected application data:** structured values such as beverage type, brand name, and alcohol
   content.
2. **Label evidence:** one or more label images associated with that application.

Because direct COLA integration is explicitly out of scope, the prototype must not assume it can
fetch either input from COLA. The P0 demo must support both of these standalone paths:

- **Preloaded synthetic record:** the user selects a provided example application whose structured
  expected values are already parsed, then attaches or opens its associated label. This is the
  fastest representative workflow and lets evaluators test without data entry.
- **Manual/ad hoc record:** the user enters the minimum expected values and uploads a label. This is
  a fallback for demonstrations and new synthetic cases, not the intended long-term operational
  workflow.

For P1 batch processing, the preferred model is a validated manifest or adapter that supplies
structured application records and label associations. The system then presents a queue that the
agent iterates, prioritizing exceptions and uncertain results. Parsing arbitrary application
documents is a separate capability and must not be silently assumed.

### 4.4 Primary workflow

1. The reviewer opens the preprocessed application queue in submission order.
2. The reviewer selects an application and sees its label evidence, expected values, and comparison
   results without re-entering application information.
3. The reviewer uses professional judgment to approve or reject the application and may add an
   optional comment.
4. The item leaves the temporary queue, the next item opens, and the reviewer can undo the action
   during the short active-session window.
5. Manual/ad hoc input remains a secondary workflow for synthetic demonstrations or exceptional
   intake.

## 5. P0 — Required prototype requirements

### 5.1 Verification intake

- **FR-001:** The application must accept one label image per verification through an obvious file
  picker and drag-and-drop target.
- **FR-002:** The application must document and enforce supported image types and a maximum file
  size. At minimum, JPEG and PNG must be supported.
- **FR-003:** The application must reject unsupported, empty, oversized, or malformed files before
  analysis and display a safe, actionable message.
- **FR-004:** The application must allow the user to preview the selected image, replace it, or
  remove it before submission.
- **FR-005:** The application must receive the beverage type—beer, wine, or distilled spirits—from
  the selected record or the ad hoc form and let the user confirm it before analysis.
- **FR-006:** The application must provide at least one complete preloaded synthetic application and
  label example for the core workflow. It must also allow an evaluator to create an ad hoc synthetic
  record without implying that manual re-entry is the intended production intake path.
- **FR-007:** The P0 intake contract must support brand name, class/type designation, net contents,
  bottler/producer name and address, country of origin for imported products, and alcohol content
  where applicable. The government-warning reference must come from the approved versioned ruleset,
  not be retyped by the agent as an expected application value.
- **FR-008:** The application must validate required form values before analysis and identify the
  specific field that needs correction. Each verification must retain a synthetic record ID, its
  intake source (`preloaded`, `ad hoc`, or later `batch`), and an unambiguous association to its
  label evidence.

### 5.2 Extraction and comparison

- **FR-009:** The application must extract readable text and relevant layout evidence from the
  uploaded label.
- **FR-010:** The application must compare brand name, class/type designation, alcohol content where
  applicable, net contents, bottler/producer name and address, country of origin for imports, and the
  government warning with the corresponding expected value or approved reference rather than merely
  displaying OCR text.
- **FR-011:** Each field must receive one of these non-final review states:
  `match`, `possible match`, `mismatch`, `not found`, `not applicable`, or `unable to evaluate`.
- **FR-012:** Brand and class/type comparison must tolerate capitalization and surrounding or repeated
  whitespace. Punctuation-only differences produce `possible match`; wording differences are
  mismatches. The original expected and detected text must remain visible for human review.
- **FR-013:** The application must not silently treat a normalized brand value as an exact match.
  For example, `STONE'S THROW` and `Stone's Throw` may be presented as equivalent or a possible
  match according to the documented rules, with both originals preserved.
- **FR-014:** Alcohol-content comparison must normalize recognized equivalent representations
  where the rule is unambiguous, such as an ABV value expressed as `% Alc./Vol.`. Proof-to-ABV
  equivalence uses the tested rule `proof = ABV × 2`; every supplied numeric value must match exactly.
- **FR-015:** Beverage-specific exceptions, including cases where alcohol content is not required,
  must be represented as explicit rules and result in `not applicable`, not a false pass or failure.
- **FR-016:** The government warning text must be compared word-for-word against a versioned,
  authoritative reference supplied or approved by the product owner. Whitespace normalization may
  be applied only if documented and must not hide missing, added, reordered, or changed words.

  The product-owner-approved P0 reference, versioned `2026-08-20`, is:

  > GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK ALCOHOLIC
  > BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF ALCOHOLIC
  > BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH
  > PROBLEMS.

  Line wrapping and runs of whitespace may be normalized for comparison; capitalization, spelling,
  punctuation, word presence, and word order must remain exact.
- **FR-017:** The application must separately evaluate whether the `GOVERNMENT WARNING:` heading
  is uppercase and whether visual evidence indicates that it is bold. If visual styling cannot be
  determined reliably, the result must be `unable to evaluate`; text recognition alone must not
  claim that boldness passed.
- **FR-018:** The application must not claim to verify font size, prominence, placement, or every
  applicable regulation unless each property has an approved, testable rule and sufficient image
  evidence.
- **FR-019:** Low-confidence, obscured, missing, or ambiguous text must be routed to manual review
  instead of being reported as a confident match or mismatch.
- **FR-020:** The result must identify which ruleset/version was used so decisions remain
  explainable when rules change.

### 5.3 Results and human review

- **FR-021:** The results page must provide a prominent summary such as `no discrepancies found`,
  `review needed`, or `analysis incomplete`. These phrases must not be presented as regulatory
  approval or rejection.
- **FR-022:** For every applicable field, the result must show the expected application value,
  detected label value, review state, and a plain-language explanation. The result must also show
  the synthetic application record ID so an agent cannot confuse results between queue items.
- **FR-023:** Results must provide evidence that lets the agent verify the finding, such as a
  highlighted image region or a clear indication that no reliable region was found.
- **FR-024:** Confidence values, if displayed, must be understandable and must not be used as a
  substitute for evidence or human judgment.
- **FR-025:** Mismatches, missing values, and uncertain findings must be visually distinct without
  relying on color alone.
- **FR-026:** The user must be able to return to the image and expected values without losing the
  current verification.
- **FR-027:** The user must be able to clear all current label and application data through an
  obvious `Start new verification` action.
- **FR-028:** The interface must display a concise disclaimer that results assist review and are
  not a final compliance determination.

### 5.4 Performance and resilience

- **NFR-001:** Under documented demo conditions, a supported single-label request must return usable
  verification results within 5 seconds, measured from submission to rendered results. The team
  must define the test image dimensions, file size, corpus, environment, network conditions, and
  percentile used for acceptance. Validation errors and dependency failures must be tracked
  separately and must not be counted as successful five-second results.
- **NFR-002:** The interface must immediately acknowledge submission and show a clear in-progress
  state without freezing or allowing duplicate submissions.
- **NFR-003:** Analysis must have a bounded timeout. A timeout must produce a retry option and an
  actionable message rather than an indefinite spinner.
- **NFR-004:** Failure of one extraction or comparison check must not erase successful field
  results; incomplete analysis must be identified explicitly.
- **NFR-005:** Runtime operation must account for restricted outbound network access. The required
  browser workflow must not make direct calls to undeclared third-party OCR or ML endpoints. Any
  server-side external dependency and required hostname must be documented, and the application
  must fail gracefully when it is unreachable.
- **NFR-006:** No essential user-interface asset, font, script, or stylesheet may depend on an
  undeclared third-party domain at runtime.

### 5.5 Usability and accessibility

- **UX-001:** The primary screen must make the next action apparent without instructions or hidden
  menus.
- **UX-002:** The core workflow must use familiar language such as `Upload label`, `Expected
  application values`, `Verify label`, and `Review needed`.
- **UX-003:** Forms must have persistent labels, helpful examples, inline validation, and a summary
  of submission errors.
- **UX-004:** The complete primary workflow must be operable by keyboard, have visible focus, and
  expose meaningful names and status changes to assistive technology.
- **UX-005:** Text, controls, focus states, and result indicators must meet WCAG 2.2 AA contrast and
  interaction expectations for the implemented workflow.
- **UX-006:** The interface must remain usable at common desktop sizes and at 200% browser zoom.
- **UX-007:** Error messages must state what happened and what the agent can do next, without stack
  traces, internal service names, or unexplained error codes.

### 5.6 Prototype data protection and security

- **SEC-001:** The prototype must use only public or synthetic application values and label images.
  The upload screen and README must warn users not to submit PII, confidential information, or real
  controlled application documents.
- **SEC-002:** Uploaded images and entered values must not be retained after the active processing
  session unless the prototype explicitly documents a short-lived technical necessity.
- **SEC-003:** Temporary data must be deleted after processing or expiry, and the retention period
  must be documented.
- **SEC-004:** Logs, analytics, and error reports must not contain uploaded image contents, OCR
  output, entered application values, credentials, or full request/response bodies.
- **SEC-005:** File type must be verified from content as well as extension. Filenames must be
  sanitized, uploads must receive generated storage identifiers, and uploaded content must never
  be executed.
- **SEC-006:** The deployed application must use HTTPS, keep secrets out of source control and
  client bundles, validate all untrusted input server-side, and return safe errors.
- **SEC-007:** Publicly reachable endpoints must have reasonable request-size, timeout, and abuse
  controls so expensive analysis cannot be invoked without bounds.
- **SEC-008:** External model or OCR providers must not receive uploaded content unless that data
  flow is explicitly documented for evaluators and is consistent with the synthetic-only scope.

### 5.7 Quality, testing, and delivery

- **QA-001:** Comparison rules must be implemented as deterministic, independently testable units
  wherever possible.
- **QA-002:** Automated tests must cover exact matches, capitalization differences, punctuation
  differences, true mismatches, missing fields, unreadable text, beverage-specific exceptions,
  warning-text deviations, warning-heading case, and indeterminate boldness.
- **QA-003:** Upload tests must cover each supported format plus malformed, mislabeled, empty,
  oversized, and unsupported files.
- **QA-004:** End-to-end tests must cover the successful primary workflow and representative
  validation, analysis, timeout, and dependency-failure paths.
- **QA-005:** Performance must be tested with a documented, synthetic label corpus; results and
  known bottlenecks must be reported in the README or approach documentation.
- **QA-006:** Test labels must include a variety of typography and layouts and must not contain real
  applicant data. The repository must record their source or generation method and permitted use.
- **QA-007:** The repository must include all source code and a README with prerequisites, local
  setup, run and test commands, architecture summary, configuration, external dependencies,
  assumptions, trade-offs, security limitations, and known verification limitations.
- **QA-008:** A working deployed prototype URL must be provided for evaluation, together with any
  supported browser constraints and synthetic example inputs needed to exercise it.
- **QA-009:** Automated checks must prevent credentials and environment-specific secrets from being
  committed.

## 6. P1 — Operationally important after the core is reliable

- **P1-001:** Allow an agent to correct extracted text and rerun comparisons without uploading the
  image again. Corrections must be visibly identified as user-entered rather than model-detected.
- **P1-002:** Provide a compact review checklist that mirrors the agents' familiar field-by-field
  process while retaining detailed evidence on demand.
- **P1-003:** Provide image zoom, pan, and evidence-region navigation for small warning text.
- **P1-004:** Let the user download or print a human-readable result summary that contains no
  uploaded image unless explicitly selected.
- **P1-005:** Add calibrated confidence thresholds and evaluate them against the synthetic corpus,
  with false matches treated as more serious than manual-review referrals.
- **P1-006:** Provide a local or self-hostable analysis option that supports the required workflow
  when outbound ML endpoints are blocked.
- **P1-007:** Display elapsed analysis time so evaluators can verify the performance objective.
- **P1-008:** Extend the prototype comparison engine with approved rules for additional conditional
  disclosures beyond the seven implemented label requirements.
- **P1-009:** Add approved checks for warning prominence, placement, and minimum type size or route
  each unsupported visual property explicitly to manual review.

### 6.1 Batch intake and review queue

- **P1-010:** Accept a batch of label images and their expected application data through a clearly
  documented manifest or multi-file workflow.
- **P1-011:** Validate the manifest schema, required values, unique record identifiers, image
  associations, and duplicate or missing files before starting the batch.
- **P1-012:** Support at least 200 labels in a batch without requiring the user to submit each one
  manually; the tested maximum must be documented.
- **P1-013:** Show batch progress and per-item states, and allow completed items to be reviewed
  while the rest continue.
- **P1-014:** A failure on one label must not fail the entire batch. Failed items must be retryable.
- **P1-015:** Batch results must be filterable by discrepancy, uncertainty, failure, and completion
  state, with a downloadable summary.
- **P1-016:** The queue must let an agent move to the next or previous application without returning
  to the intake screen, and must preserve the user's position during the active session.
- **P1-017:** The queue should prioritize mismatches, uncertainty, and failures while allowing the
  user to restore original submission order.
- **P1-018:** Batch performance targets must be defined separately from the five-second interactive
  single-label target.
- **P1-019:** The P1 batch workflow must operate without PostgreSQL or another required database.
  Queue state and results may be session-scoped, and the interface must state that a server restart
  or expired session can discard unfinished work.

Batch handling is P1 rather than P2 because the compliance lead identified 200–300-application
submissions as a longstanding operational problem. It remains outside P0 only because the project
brief explicitly prefers a complete working core over ambitious incomplete features.

## 7. P2 — Stretch goals

### 7.1 Difficult-image assistance

- **ST-001:** Detect likely skew, glare, blur, low contrast, poor lighting, occlusion, and
  insufficient resolution before or during analysis.
- **ST-002:** Apply non-destructive perspective or image-quality corrections when they measurably
  improve extraction, while retaining the original image for comparison.
- **ST-003:** Explain image-quality problems and suggest a better capture when reliable extraction
  remains impossible.
- **ST-004:** Difficult-image features must be evaluated on a labeled synthetic test set and must
  not turn unreadable content into a confident invented value.

### 7.2 Additional enhancements

- **ST-005:** Expand the versioned rules engine to additional beverage-specific layout, wording,
  or presentation requirements beyond the P1 field set only after authoritative rules and test
  examples are approved.
- **ST-006:** Support multi-panel, bottle-wrap, and multi-image submissions while preserving which
  image region supports each result.
- **ST-007:** Offer multilingual assistance where allowed, without translating text that must be
  compared verbatim.

### 7.3 Durable persistence

- **ST-008:** Add PostgreSQL-backed persistence only if the product needs resumable batches,
  cross-session history, durable result retrieval, or multiple workers coordinating queue state.
- **ST-009:** If durable persistence is added, define retention and deletion behavior before storing
  any image, extracted text, application value, or result.
- **ST-010:** A persisted batch must recover safely after a process restart without duplicating or
  losing completed work.

## 8. Explicitly out of scope for this prototype

- Direct integration with COLA or any other government system.
- Production use with real label applications, PII, or controlled documents.
- Automatic submission, approval, rejection, enforcement, or alteration of an application.
- A complete replacement for a compliance agent's regulatory judgment.
- A claim that all TTB rules are covered without an approved, versioned rule inventory.
- A modernization or replacement of the existing COLA platform.
- Production accreditation, authorization, or FedRAMP certification.

## 9. Future production requirements

Before use in an operational environment, the product would require a separate production
assessment and, at minimum:

- Approved identity, authentication, role-based authorization, least privilege, and session
  management.
- Tenant or organizational data isolation where applicable.
- Formal data classification, privacy impact, records-retention, legal-hold, deletion, and audit
  requirements for application documents and PII.
- Encryption in transit and at rest, approved key and secret management, vulnerability management,
  dependency governance, incident response, backup, recovery, and continuity controls.
- An append-only audit trail for access, rule versions, model versions, user corrections, and final
  human decisions, without unsafe document content in operational logs.
- Azure and federal hosting/security review, including applicable authorization and FedRAMP
  requirements; the interview does not establish the exact required authorization boundary.
- Formal review and approval of all regulatory rules by qualified policy owners, plus a controlled
  process for rule updates and effective dates.
- Model/OCR validation, bias and failure analysis, monitoring for accuracy and latency drift,
  rollback capability, and a human-review fallback.
- Capacity planning for approximately 150,000 annual applications and importer submissions of
  200–300 labels, with availability and recovery objectives set by operations.
- Network architecture that works with the agency firewall and uses only allowlisted endpoints.
- Accessibility testing with representative users, including less technically confident agents.
- Procurement, licensing, intellectual-property, vendor data-use, and service-level review for all
  third-party components.

## 10. Architecture and implementation constraints

- Keep image extraction, field normalization, comparison rules, and result presentation as
  separable components so each can be tested and replaced independently.
- Prefer deterministic code for known comparisons and calculations. Use probabilistic extraction
  only where needed, expose uncertainty, and never ask a generative model to invent unreadable
  label content.
- Treat the server as the authority for validation and comparison; client-side validation may
  improve usability but cannot be the only enforcement.
- Version rules, extraction/model configuration, and result schemas to support reproducibility.
- Keep P0 and P1 runnable without PostgreSQL or another database. Use version-controlled synthetic
  fixtures and bounded request- or session-scoped state; introduce durable storage only for P2 or a
  future production requirement.
- Do not make the browser depend directly on secret-bearing third-party APIs.
- Make external analysis dependencies configurable and observable, with bounded retries and safe
  circuit-breaking behavior.
- Collect only operational metrics needed to evaluate the prototype, such as sanitized request ID,
  duration, outcome category, and dependency status. Do not collect document contents.

## 11. Acceptance scenarios

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| AC-01 | A clear synthetic distilled-spirits label matches all supplied application values | All supported fields show their evidence and appropriate match state; the summary does not claim regulatory approval; the response meets the documented five-second target. |
| AC-02 | Brand differs only in capitalization | Both original values are shown and the documented normalization rule is explained; the result does not report a misleading textual mismatch. |
| AC-03 | Brand differs in potentially meaningful punctuation or wording | The field is marked `possible match` or `review needed`, with both values and evidence visible. |
| AC-04 | Warning wording has one changed, missing, added, or reordered word | Warning text is marked as a mismatch and the difference is identifiable. |
| AC-05 | Warning heading is title case | Heading-case check is marked as a mismatch even if the warning body is otherwise exact. |
| AC-06 | OCR finds the warning text but visual analysis cannot establish boldness | Text and boldness are reported separately; boldness is `unable to evaluate` and requires review. |
| AC-07 | Label is blurry or affected by glare | The system does not invent values; uncertain fields are referred to manual review and the user receives useful recapture guidance. |
| AC-08 | A required application value or valid image is absent | Analysis does not start, and the relevant input has an actionable validation message. |
| AC-09 | The analysis dependency is blocked by the network or times out | The interface stops waiting within the bounded timeout, preserves any safe partial results, and offers a retry or documented fallback. |
| AC-10 | The user starts a new verification | Previous image, entered values, extracted text, and results are cleared and are not visible in the new workflow. |
| AC-11 | A keyboard-only user completes the core workflow at 200% zoom | All controls and results remain reachable, understandable, and operable with visible focus. |
| AC-12 | An evaluator selects the supplied synthetic application | Expected core values are populated from the record with source/provenance shown; the evaluator does not need to retype them. |
| AC-13 | An evaluator creates an ad hoc synthetic application | The evaluator can enter the minimum expected values and attach a label without needing COLA access. |
| AC-14 | A P1 batch contains valid records plus one missing image | The manifest issue is identified before processing; valid associations remain intact and the user can correct the missing-image record. |
| AC-15 | An agent reviews a completed P1 batch | The agent can filter to review-needed records, move through them without re-entry, and restore original submission order. |

## 12. Open decisions requiring product-owner confirmation

These gaps must be resolved before their related checks can be called complete:

1. **Resolved for P0:** The product owner supplied the exact prototype warning reference on
   2026-08-20. Independent regulatory provenance remains required before production use.
2. Which beverage-specific rules and exceptions are included in the prototype, beyond the three
   emphasized checks of brand, alcohol content, and government warning?
3. Should capitalization-only brand differences be a `match` or `possible match`, and which other
   punctuation, abbreviation, or Unicode normalization rules are acceptable?
4. Which application fields are mandatory for each beverage type and import status?
5. What image dimensions, maximum file size, supported browsers, test environment, and percentile
   define the five-second acceptance target?
6. Is a runtime cloud OCR/ML provider acceptable for the deployed demo? If so, which domains,
   retention terms, regions, and data-use terms are approved?
7. May prototype inputs exist briefly in memory or temporary storage, and what exact expiry is
   acceptable?
8. Is P1 batch intake expected in the evaluated deliverable after P0 is complete, and what
   file-to-application-data mapping format is preferred?
9. What accuracy thresholds are acceptable for each field, and what maximum false-match rate is
   tolerable?
10. Is detecting bold warning text required for prototype acceptance, or is an explicit manual
    review state acceptable when styling cannot be determined?
11. In a future operational workflow, will expected values arrive through a structured export,
    internal API, uploaded manifest, or pre-parsed queue? Who owns and validates that upstream
    parsing?
12. Does each application have one label image, multiple panels/images, or both, and how are those
    assets associated with the application record?
13. What event would justify promoting durable PostgreSQL persistence from P2—for example resumable
    batches, cross-session history, multi-user work assignment, or audit retention?

Until these decisions are answered, the application must use conservative behavior, document its
assumptions, and route uncertain cases to human review.

## 13. Stakeholder concern traceability

| Stakeholder/source concern | Requirement coverage |
| --- | --- |
| Agents spend substantial time matching application data to label data | G-01, FR-006–FR-020 |
| Results slower than about five seconds will not be adopted | G-02, NFR-001–NFR-004, P1-007 |
| Agents have widely varying technical comfort and half are over 50 | User-demographics section, G-04, UX-001–UX-007, P1-002 |
| Importers submit 200–300 labels at once | P1-010–P1-019, AC-14–AC-15, and future capacity planning |
| Agents should not be burdened with more data entry | Input-sources section, G-01, FR-005–FR-008, AC-12–AC-13 |
| Prototype is standalone and must not integrate with COLA | Out-of-scope boundaries |
| Government networks may block outbound ML endpoints | NFR-005–NFR-006, P1-006, open decision 6 |
| Production would involve PII, retention, and federal controls | SEC-001–SEC-008, future production requirements |
| Label matching requires nuance and agent judgment | G-03, FR-011–FR-013, FR-019, FR-021–FR-028 |
| Government warning wording must be exact | FR-016, QA-002, AC-04 |
| Warning heading must be uppercase and bold | FR-017, AC-05–AC-06, open decision 10 |
| Warning text may be made too small or buried in the design | FR-018, P1-003, P1-009 |
| Agents currently rely on a familiar printed checklist | UX-001–UX-003, P1-002 |
| Label images may have skew, glare, poor lighting, or low readability | FR-019, ST-001–ST-004, AC-07 |
| Requirements vary among beer, wine, and distilled spirits | FR-005–FR-007, FR-015, P1-008–P1-009, ST-005, open decisions 2 and 4 |
| Common label elements include brand, class/type, ABV, net contents, producer, origin, and warning | P0 scope, FR-007–FR-020, P1-008–P1-009 |
| Reviewers expect clean code, appropriate choices, error handling, and completeness | NFR, UX, SEC, QA, and architecture sections |
| A working core is preferred to incomplete ambition | Priority model; P0 precedes P1 and P2 |
| Synthetic/generated labels may supplement the provided example | SEC-001, QA-005–QA-006 |
| Repository, documentation, and deployed URL are required deliverables | G-05, QA-007–QA-008 |
