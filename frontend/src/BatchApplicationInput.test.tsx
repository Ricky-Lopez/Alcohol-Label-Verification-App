import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { BatchApplicationInput } from './BatchApplicationInput'

const pendingBatch = {
  batchId: 'batch-1', status: 'processing', totalCount: 1, processedCount: 0,
  readyCount: 0, failedCount: 0, skippedCount: 0, createdAt: '2026-08-24T00:00:00Z',
  completedAt: null, sessionScoped: true,
  items: [{ batchItemId: 'item-1', rowNumber: 2, filename: 'label.png', recordId: 'record-1', brandName: 'OLD TOM DISTILLERY', status: 'pending', overallStatus: null, queueItemId: null, errorCode: null, errorMessage: null, retryable: false, durationMs: null }]
}
const completedBatch = {
  ...pendingBatch, status: 'completed', processedCount: 1, readyCount: 1,
  completedAt: '2026-08-24T00:00:02Z',
  items: [{ ...pendingBatch.items[0], status: 'ready_for_review', overallStatus: 'no_discrepancies_found', queueItemId: 'queue-7', durationMs: 2000 }]
}
const pausedBatch = {
  ...pendingBatch, status: 'paused', processedCount: 1, failedCount: 1,
  items: [{ ...pendingBatch.items[0], status: 'failed', errorCode: 'ocr_504', errorMessage: 'Image analysis timed out. Try again.', retryable: true, durationMs: 300000 }]
}
const skippedBatch = {
  ...pausedBatch, status: 'completed_with_errors', failedCount: 0, skippedCount: 1,
  completedAt: '2026-08-24T00:05:00Z',
  items: [{ ...pausedBatch.items[0], status: 'skipped', retryable: false }]
}

const selectFiles = () => {
  const csv = new File(['manifest'], 'applications.csv', { type: 'text/csv' })
  const image = new File(['image'], 'label.png', { type: 'image/png' })
  fireEvent.change(document.getElementById('batch-csv')!, { target: { files: [csv] } })
  fireEvent.change(document.getElementById('batch-images')!, { target: { files: [image] } })
}

describe('BatchApplicationInput', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it('focuses a complete error summary before attempting an empty batch', () => {
    render(<BatchApplicationInput onOpenHub={vi.fn()} onReviewNow={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Validate and process batch' }))

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Choose one CSV application file.')
    expect(alert).toHaveTextContent('Choose at least one label image.')
    expect(document.activeElement).toBe(alert)
  })

  it('shows incremental completion and opens the ready queue item', async () => {
    const onReviewNow = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/batches' && init?.method === 'POST') return Promise.resolve(new Response(JSON.stringify(pendingBatch), { status: 201 }))
      if (url.includes('/process')) return Promise.resolve(new Response(JSON.stringify(completedBatch), { status: 200 }))
      if (url === '/api/batches/batch-1') return Promise.resolve(new Response(JSON.stringify(completedBatch), { status: 200 }))
      return Promise.reject(new Error('unexpected request'))
    }))
    render(<BatchApplicationInput onOpenHub={vi.fn()} onReviewNow={onReviewNow} />)
    selectFiles()
    fireEvent.click(screen.getByRole('button', { name: 'Validate and process batch' }))

    expect(await screen.findByRole('heading', { name: 'Batch processing complete' })).toBeInTheDocument()
    expect(screen.getByText('Ready for human review: 1 of 1')).toBeInTheDocument()
    expect(screen.getByText('No discrepancies found')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review now' }))
    expect(onReviewNow).toHaveBeenCalledWith('queue-7')
    expect(screen.getByRole('link', { name: 'Download results CSV' })).toHaveAttribute('href', '/api/batches/batch-1/results.csv')
  })

  it('pauses on failure and finishes with errors after an explicit skip', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/batches' && init?.method === 'POST') return Promise.resolve(new Response(JSON.stringify(pendingBatch), { status: 201 }))
      if (url.includes('/process')) return Promise.resolve(new Response(JSON.stringify(pausedBatch), { status: 504 }))
      if (url.endsWith('/skip')) return Promise.resolve(new Response(JSON.stringify(skippedBatch), { status: 200 }))
      if (url === '/api/batches/batch-1') return Promise.resolve(new Response(JSON.stringify(pausedBatch), { status: 200 }))
      return Promise.reject(new Error('unexpected request'))
    }))
    render(<BatchApplicationInput onOpenHub={vi.fn()} onReviewNow={vi.fn()} />)
    selectFiles()
    fireEvent.click(screen.getByRole('button', { name: 'Validate and process batch' }))

    expect(await screen.findByRole('heading', { name: 'Batch processing paused' })).toBeInTheDocument()
    expect(screen.getByText(/Resolve every failed application/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Skip and continue' }))
    expect(await screen.findByRole('heading', { name: 'Batch processing complete with errors' })).toBeInTheDocument()
    expect(screen.getAllByText('Skipped')).toHaveLength(2)
  })
})
