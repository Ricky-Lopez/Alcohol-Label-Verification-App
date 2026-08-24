import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { exampleApplication } from './exampleApplication'

const healthyService = () => new Response(JSON.stringify({ status: 'ok', service: 'alcohol-label-verification-api' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
const openApplicationInput = () => fireEvent.click(screen.getAllByRole('button', { name: 'Single Application Input' })[0]!)

describe('App', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it('shows a visible, non-blocking service state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(healthyService()))
    render(<App />)
    openApplicationInput()
    expect(await screen.findByText('Verification service is available.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Expected application values' })).toBeInTheDocument()
  })

  it('links blank required values to an error summary and moves focus there', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(healthyService()))
    render(<App />)
    openApplicationInput()
    fireEvent.click(screen.getByRole('button', { name: 'Continue to upload label' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Brand name is required.')
    expect(document.activeElement).toBe(screen.getByRole('alert'))
    expect(screen.getByRole('link', { name: 'Brand name is required.' })).toHaveAttribute('href', '#brandName')
  })

  it('loads the synthetic example and reveals imported-product fields only when needed', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(healthyService()))
    render(<App />)
    openApplicationInput()
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }))
    expect(screen.getByDisplayValue('OLD TOM DISTILLERY')).toBeInTheDocument()
    expect(document.getElementById('originDisplayName')).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('This is an imported product'))
    expect(document.getElementById('originDisplayName')).toBeInTheDocument()
  })

  it('rejects unsupported image files before analysis', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(healthyService()))
    render(<App />)
    openApplicationInput()
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue to upload label' }))
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['text'], 'label.txt', { type: 'text/plain' })] } })
    expect(document.getElementById('image-error')).toHaveTextContent('Choose a JPEG or PNG image.')
    expect(screen.getByRole('button', { name: 'Verify label' })).toBeDisabled()
  })

  it('compares a completed OCR extraction and presents decision-support findings', async () => {
    const extraction = { extractionId: 'extraction-1', submissionId: 'submission-1', status: 'succeeded', extractor: { name: 'mock', version: '1' }, durationMs: 1, timing: { imagePreparationMs: 0, providerMs: 1 }, segments: [], fieldCandidates: [], issues: [] }
    const comparison = { verificationId: 'verification-1', submissionId: 'submission-1', recordId: 'record-1', overallStatus: 'review_needed', decisionSupportOnly: true, ruleset: { rulesetId: 'alcohol-label-prototype', version: '2026-08-20', effectiveDate: '2026-08-20' }, extractor: { name: 'mock', version: '1' }, findings: [{ field: 'brand_name', outcome: 'possible_match', severity: 'review', ruleId: 'brand-name-v1', explanation: 'Review the punctuation.', expected: { displayValue: 'Old Tom' }, detected: [{ displayValue: 'Old-Tom' }] }], startedAt: '2026-08-20T00:00:00Z', completedAt: '2026-08-20T00:00:00Z', durationMs: 1 }
    const queueDetail = { summary: { queueItemId: 'ad-hoc-item-1', position: 7, recordId: 'record-1', brandName: 'OLD TOM DISTILLERY', beverageType: 'distilled spirits', overallStatus: 'review_needed', attentionCount: 1, queuedAt: '2026-08-23T00:00:00Z', version: 1 }, application: { ...exampleApplication, recordId: 'record-1' }, verification: comparison, images: [{ imageId: 'image-1', panelType: 'unknown', altText: 'Submitted label', imageUrl: '/api/review-queue/ad-hoc-item-1/images/image-1' }] }
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/health') return Promise.resolve(healthyService())
      if (url === '/api/extractions') return Promise.resolve(new Response(JSON.stringify(extraction), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      if (url === '/api/comparisons') return Promise.resolve(new Response(JSON.stringify(comparison), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      if (url === '/api/review-queue' && init?.method === 'POST') return Promise.resolve(new Response(JSON.stringify(queueDetail), { status: 201, headers: { 'Content-Type': 'application/json' } }))
      if (url === '/api/review-queue') return Promise.resolve(new Response(JSON.stringify({ items: [queueDetail.summary], totalCount: 1, sessionScoped: true }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      if (url === '/api/review-queue/ad-hoc-item-1') return Promise.resolve(new Response(JSON.stringify(queueDetail), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      return Promise.resolve(new Response(JSON.stringify(comparison), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    openApplicationInput()
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue to upload label' }))
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['image'], 'label.png', { type: 'image/png' })] } })
    expect(screen.queryByLabelText('Label panel')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Verify label' }))

    expect(await screen.findByRole('heading', { name: 'Review needed' })).toBeInTheDocument()
    expect(screen.getByText('Application added to the Reviewer Hub.')).toBeInTheDocument()
    expect(screen.getByText('Review the punctuation.')).toBeInTheDocument()
    expect(screen.getAllByText(/not a final compliance determination/i)).toHaveLength(2)
    const queueCall = fetchMock.mock.calls.find(([url, options]) => String(url) === '/api/review-queue' && options?.method === 'POST')
    expect(queueCall?.[1]?.body).toBeInstanceOf(FormData)

    fireEvent.click(screen.getByRole('button', { name: 'Review this application now' }))
    expect(await screen.findByRole('heading', { name: 'OLD TOM DISTILLERY' })).toBeInTheDocument()
    expect(screen.getByText('Submitted label image')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Reviewer Hub' }))
    expect(await screen.findByRole('heading', { name: 'Reviewer Hub' })).toBeInTheDocument()
    expect(screen.getByText('1 applications in queue')).toBeInTheDocument()
  })

  it('makes Reviewer Hub the primary home workflow', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Choose a workspace' })).toBeInTheDocument()
    expect(screen.getByText('Open Reviewer Hub')).toBeInTheDocument()
    expect(screen.getByText('Side feature')).toBeInTheDocument()
  })
})
