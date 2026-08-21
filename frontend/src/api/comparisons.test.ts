import { describe, expect, it } from 'vitest'

import { requestComparison } from './comparisons'
import type { OcrExtractionResult, VerificationSubmission } from './generated/verification'

const submission: VerificationSubmission = {
  submissionId: 'submission-1',
  application: { schemaVersion: '1.0', recordId: 'record-1', intakeSource: 'ad_hoc', beverageType: 'distilled_spirits', imported: false, expectedLabel: { brandName: 'Example', classTypeDesignation: 'Whiskey', alcoholContent: { abvPercent: 45 }, netContents: { value: 750, unit: 'mL' }, responsibleParties: [{ name: 'Example Co', address: { city: 'Austin', countryCode: 'US' } }] } },
  images: [{ clientImageId: 'image-1', fileName: 'label.png', mediaType: 'image/png', sizeBytes: 4 }]
}

const extraction: OcrExtractionResult = { extractionId: 'extraction-1', submissionId: 'submission-1', status: 'succeeded', extractor: { name: 'mock', version: '1' }, durationMs: 1, timing: { imagePreparationMs: 0, providerMs: 1 }, segments: [], fieldCandidates: [], issues: [] }

describe('requestComparison', () => {
  it('sends the original submission and extraction as JSON', async () => {
    let request: RequestInit | undefined
    const fetchImplementation = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      request = init
      return new Response(JSON.stringify({ verificationId: 'verification-1', submissionId: 'submission-1', recordId: 'record-1', overallStatus: 'review_needed', decisionSupportOnly: true, ruleset: { rulesetId: 'alcohol-label-prototype', version: '2026-08-20', effectiveDate: '2026-08-20' }, extractor: { name: 'mock', version: '1' }, findings: [{ field: 'brand_name', outcome: 'match', severity: 'information', ruleId: 'brand-name-v1', explanation: 'Matched' }], startedAt: '2026-08-20T00:00:00Z', completedAt: '2026-08-20T00:00:00Z', durationMs: 1 }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }) as typeof fetch

    const outcome = await requestComparison(submission, extraction, { fetchImplementation })

    expect(outcome.kind).toBe('completed')
    expect(new Headers(request?.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(String(request?.body))).toMatchObject({ submission, extraction })
  })
})
