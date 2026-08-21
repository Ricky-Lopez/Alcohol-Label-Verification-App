import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ReviewerHub } from './ReviewerHub'

const queue = { totalCount: 3, sessionScoped: true, items: [{ queueItemId: 'item-1', position: 1, recordId: 'record-1', brandName: 'FIRST BRAND', beverageType: 'distilled spirits', overallStatus: 'review_needed', attentionCount: 1, queuedAt: '2026-08-21T00:00:00Z', version: 1 }, { queueItemId: 'item-2', position: 2, recordId: 'record-2', brandName: 'SECOND BRAND', beverageType: 'distilled spirits', overallStatus: 'no_discrepancies_found', attentionCount: 0, queuedAt: '2026-08-21T00:00:00Z', version: 1 }, { queueItemId: 'item-3', position: 3, recordId: 'record-3', brandName: 'INCOMPLETE BRAND', beverageType: 'wine', overallStatus: 'analysis_incomplete', attentionCount: 2, queuedAt: '2026-08-21T00:00:00Z', version: 1 }] }
const detail = { summary: queue.items[0], application: { schemaVersion: '1.0', recordId: 'record-1', intakeSource: 'batch', beverageType: 'distilled_spirits', imported: false, expectedLabel: { brandName: 'FIRST BRAND', classTypeDesignation: 'Whiskey', alcoholContent: { abvPercent: 45 }, netContents: { value: 750, unit: 'mL' }, responsibleParties: [{ name: 'Example Co', address: { city: 'Austin', countryCode: 'US' } }] } }, verification: { verificationId: 'verification-1', submissionId: 'submission-1', recordId: 'record-1', overallStatus: 'review_needed', decisionSupportOnly: true, ruleset: { rulesetId: 'prototype', version: '1', effectiveDate: '2026-08-21' }, extractor: { name: 'mock', version: '1' }, findings: [{ field: 'brand_name', outcome: 'mismatch', severity: 'discrepancy', ruleId: 'brand', explanation: 'Different brand.' }], startedAt: '2026-08-21T00:00:00Z', completedAt: '2026-08-21T00:00:00Z', durationMs: 1 }, images: [{ imageId: 'image-1', panelType: 'brand', altText: 'First label', imageUrl: '/image.svg' }] }

describe('ReviewerHub', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it('lists applications in submission order and opens a focused review workspace', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo | URL) => Promise.resolve(new Response(JSON.stringify(String(input) === '/api/review-queue' ? queue : detail), { status: 200, headers: { 'Content-Type': 'application/json' } }))))
    render(<ReviewerHub onHome={vi.fn()} />)

    expect(await screen.findByText('FIRST BRAND')).toBeInTheDocument()
    expect(screen.getByText('SECOND BRAND')).toBeInTheDocument()
    expect(screen.getByText('INCOMPLETE BRAND')).toBeInTheDocument()
    expect(screen.getAllByText('Review needed')).toHaveLength(3)
    expect(screen.queryByText('Analysis incomplete: automated evidence is limited')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('FIRST BRAND'))

    expect(await screen.findByRole('heading', { name: 'FIRST BRAND' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve application' })).toBeInTheDocument()
    expect(screen.getByText(/Use ← and →/)).toBeInTheDocument()
  })
})
