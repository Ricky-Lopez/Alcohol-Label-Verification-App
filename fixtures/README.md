# Synthetic fixtures

Only public or synthetic application records and label images belong in this directory.

`applications/example-distilled-spirits-submission.json` is a complete frontend submission example
validated by the backend model tests. Its referenced image name is synthetic metadata; a matching
generated image will be added when the upload and extraction slice is implemented.

`applications/example-reviewer-queue-batch.csv` is a ready-to-upload batch manifest for these two
synthetic label images:

- `reviewer_queue/01-old-tom-distillery.png`
- `reviewer_queue/02-meadowlark-rye.png`

Open **Batch Application Input**, select the CSV, then select both images. The record IDs deliberately
differ from the pre-seeded Reviewer Hub records so the batch can be accepted while those examples
remain in the queue. The expected values match the visible synthetic labels and should produce no
discrepancies when OCR extracts every field accurately. The fixed `success` mock scenario always
returns the Old Tom observation set, so use live OCR to assess both images rather than treating the
mock as an image-reading accuracy test.

`extractions/mock-scenarios.json` is the shared catalog of deterministic mock-provider scenarios,
HTTP statuses, extraction statuses, and primary issue codes. Backend route tests consume this file,
and future frontend browser tests can use the same scenario names through the mock-only
`X-OCR-Mock-Scenario` header.

`ocr_evaluation/` is a deterministic synthetic corpus for opt-in live OCR evaluation. The PNGs are
generated from `generate_labels.py`; its manifest records each expected application and intended
comparison category. The complete warning text is software-rendered rather than AI-rendered, so
spelling and punctuation are controlled. Run it only with `OCR_PROVIDER=openai`:

```bash
cd backend
OCR_PROVIDER=openai uv run python -m app.extraction.evaluation \
  --fixture-dir ../fixtures/ocr_evaluation
```

The command reports statuses and timing metrics without printing extracted label text or provider
responses. The current five-minute OCR timeout is temporary for this optimization work and must be
reduced after measurements establish an interactive production target.

`reviewer_queue/` contains the synthetic, preprocessed examples displayed by the Reviewer Hub.
Five use the full approved warning text; Harvest Moon deliberately uses an incomplete warning as the
intentional warning-failure case.
