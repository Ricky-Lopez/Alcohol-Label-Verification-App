import { afterEach, describe, expect, it, vi } from 'vitest'

import { exampleApplication } from '../exampleApplication'
import type {
  ReviewQueueItemDetail,
  VerificationResult,
  VerificationSubmission
} from './generated/verification'
import { enqueueReviewQueueItem } from './reviewQueue'

const submission: VerificationSubmission = {
  submissionId: 'submission-1',
  application: { ...exampleApplication, recordId: 'record-1' },
  images: [{
    clientImageId: 'image-1',
    fileName: 'label.png',
    mediaType: 'image/png',
    sizeBytes: 5,
    panelType: 'unknown'
  }]
}

const verification: VerificationResult = {
  schemaVersion: '1.0',
  verificationId: 'verification-1',
  submissionId: 'submission-1',
  recordId: 'record-1',
  overallStatus: 'no_discrepancies_found',
  decisionSupportOnly: true,
  ruleset: { rulesetId: 'prototype', version: '1', effectiveDate: '2026-08-23' },
  extractor: { name: 'mock', version: '1' },
  findings: [{
    field: 'brand_name',
    outcome: 'match',
    severity: 'information',
    ruleId: 'brand-name-v1',
    explanation: 'The brand name matches.'
  }],
  startedAt: '2026-08-23T00:00:00Z',
  completedAt: '2026-08-23T00:00:00Z',
  durationMs: 1
}

const detail: ReviewQueueItemDetail = {
  summary: {
    queueItemId: 'queue-item-1',
    position: 1,
    recordId: 'record-1',
    brandName: exampleApplication.expectedLabel.brandName,
    beverageType: 'distilled spirits',
    overallStatus: 'no_discrepancies_found',
    attentionCount: 0,
    queuedAt: '2026-08-23T00:00:00Z',
    version: 1
  },
  application: submission.application,
  verification,
  images: [{
    imageId: 'image-1',
    panelType: 'unknown',
    altText: 'Submitted label',
    imageUrl: '/api/review-queue/queue-item-1/images/image-1'
  }]
}

describe('enqueueReviewQueueItem', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends the processed application and image as multipart data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(detail), {
      status: 201,
      headers: { 'Content-Type': 'application/json' }
    }))
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['image'], 'label.png', { type: 'image/png' })

    const outcome = await enqueueReviewQueueItem(submission, verification, {
      file,
      previewUrl: 'blob:label',
      metadata: submission.images[0]
    })

    expect(outcome).toEqual({ kind: 'completed', value: detail })
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/review-queue')
    expect(options.method).toBe('POST')
    expect(new Headers(options.headers).has('Content-Type')).toBe(false)
    const body = options.body as FormData
    expect(JSON.parse(String(body.get('payload')))).toEqual({ submission, verification })
    const uploadedImage = body.get('image') as File
    expect(uploadedImage.name).toBe('label.png')
    expect(uploadedImage.type).toBe('image/png')
    expect(uploadedImage.size).toBe(file.size)
  })
})
