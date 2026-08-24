# Live OCR Fixture Evaluation

Date: 2026-08-23

Provider: OpenAI Responses API

Configured model: `gpt-4o-mini`

Corpus: `fixtures/reviewer_queue/`

Runs per fixture: 1

This report records field outcomes without retaining image data, provider response bodies, prompts,
expected label values, or raw OCR text. Live vision output is nondeterministic; these results are a
single diagnostic pass rather than a permanent accuracy guarantee.

## Overall results

| Fixture | Intended status | Actual status | Provider time |
| --- | --- | --- | ---: |
| Old Tom Distillery | No discrepancies found | Review needed | 5,667 ms |
| Meadowlark Rye | No discrepancies found | Review needed | 3,883 ms |
| Stone's Throw | Review needed | Review needed | 5,458 ms |
| Riverbend Bourbon | Review needed | Review needed | 4,848 ms |
| Harvest Moon Spirits | Analysis incomplete | Review needed | 7,005 ms |
| Cedar Ridge Whiskey | Analysis incomplete | Review needed | 5,335 ms |

## Per-field findings

| Fixture | Brand | Class/type | Alcohol | Net contents | Party name | Party address | Origin | Warning text | Heading case | Heading weight |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Old Tom | Mismatch | Mismatch | Match | Match | Match | Match | Not applicable | Match | Match | Match |
| Meadowlark | Mismatch | Match | Match | Match | Match | Match | Not applicable | Match | Match | Match |
| Stone's Throw | Mismatch | Match | Match | Match | Match | Match | Not applicable | Match | Match | Match |
| Riverbend | Mismatch | Match | Mismatch | Match | Match | Match | Not applicable | Match | Match | Match |
| Harvest Moon | Mismatch | Match | Match | Match | Match | Match | Not applicable | Mismatch | Match | Match |
| Cedar Ridge | Mismatch | Mismatch | Match | Match | Match | Match | Not applicable | Mismatch | Match | Match |

Each field produced one OCR candidate when applicable. The non-imported country-of-origin finding
was correctly `not_applicable`; the first four extractions nevertheless included a low-confidence
origin candidate that did not affect the comparison outcome. No global extraction issue occurred.

## Observations

- Brand extraction mismatched in all six cases and is the primary systematic failure.
- The complete government warning matched in Old Tom, Meadowlark, Stone's Throw, and Riverbend.
- Harvest Moon's intentionally incomplete warning correctly produced a text mismatch, but OCR did
  not mark it incomplete; the resulting status was `review_needed`, not `analysis_incomplete`.
- Cedar Ridge's obscured warning produced a mismatch, but OCR did not mark the visual evidence
  uncertain; it also remained `review_needed` rather than `analysis_incomplete`.
- Riverbend's intended alcohol-content mismatch was detected.
- Comparison execution rounded to zero milliseconds for every fixture; provider inference remains
  the material latency source.
