import { describe, expect, it } from 'vitest'

import { requestExtraction, type PendingLabelImage } from './extractions'
import type { VerificationSubmission } from './generated/verification'

const submission: VerificationSubmission = {
  submissionId: 'submission-1',
  application: { schemaVersion: '1.0', recordId: 'record-1', intakeSource: 'ad_hoc', beverageType: 'distilled_spirits', imported: false, expectedLabel: { brandName: 'Example', classTypeDesignation: 'Whiskey', alcoholContent: { abvPercent: 45 }, netContents: { value: 750, unit: 'mL' }, responsibleParties: [{ name: 'Example Co', address: { city: 'Austin', countryCode: 'US' } }] } },
  images: [{ clientImageId: 'image-1', fileName: 'label.png', mediaType: 'image/png', sizeBytes: 4 }]
}
const image: PendingLabelImage = { file: new File(['test'], 'label.png', { type: 'image/png' }), previewUrl: 'blob:test', metadata: submission.images[0] }

describe('requestExtraction', () => {
  it('uses ordered multipart fields without overriding the multipart content type', async () => {
    let request: RequestInit | undefined
    const fetchImplementation = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      request = init
      return new Response(JSON.stringify({ extractionId: 'extraction-1', submissionId: 'submission-1', status: 'succeeded', extractor: { name: 'mock-ocr', version: '1.0.0' }, durationMs: 1, segments: [], fieldCandidates: [], issues: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }) as typeof fetch
    const outcome = await requestExtraction(submission, image, { fetchImplementation, mockScenario: 'success' })
    expect(outcome.kind).toBe('completed')
    expect(new Headers(request?.headers).get('Content-Type')).toBeNull()
    expect(new Headers(request?.headers).get('X-OCR-Mock-Scenario')).toBe('success')
    const body = request?.body as FormData
    expect(JSON.parse(String(body.get('submission')))).toEqual(submission)
    expect((body.get('images') as File).name).toBe('label.png')
  })

  it('keeps a typed provider failure instead of reducing it to a generic error', async () => {
    const fetchImplementation = (async () => new Response(JSON.stringify({ extractionId: 'extraction-1', submissionId: 'submission-1', status: 'failed', extractor: { name: 'mock-ocr', version: '1.0.0' }, durationMs: 1, segments: [], fieldCandidates: [], issues: [{ code: 'extractor_timeout', message: 'Timed out' }] }), { status: 504, headers: { 'Content-Type': 'application/json' } })) as typeof fetch
    const outcome = await requestExtraction(submission, image, { fetchImplementation })
    expect(outcome).toMatchObject({ kind: 'provider-failure', httpStatus: 504 })
  })
})
