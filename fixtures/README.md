# Synthetic fixtures

Only public or synthetic application records and label images belong in this directory.

`applications/example-distilled-spirits-submission.json` is a complete frontend submission example
validated by the backend model tests. Its referenced image name is synthetic metadata; a matching
generated image will be added when the upload and extraction slice is implemented.

`extractions/mock-scenarios.json` is the shared catalog of deterministic mock-provider scenarios,
HTTP statuses, extraction statuses, and primary issue codes. Backend route tests consume this file,
and future frontend browser tests can use the same scenario names through the mock-only
`X-OCR-Mock-Scenario` header.
