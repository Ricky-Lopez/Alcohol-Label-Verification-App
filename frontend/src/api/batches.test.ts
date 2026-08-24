import { afterEach, describe, expect, it, vi } from 'vitest'

import { createBatch, processBatchItem, skipBatchItem } from './batches'

const detail = {
  batchId: 'batch-1', status: 'processing', totalCount: 1, processedCount: 0,
  readyCount: 0, failedCount: 0, skippedCount: 0, createdAt: '2026-08-24T00:00:00Z',
  completedAt: null, sessionScoped: true,
  items: [{ batchItemId: 'item-1', rowNumber: 2, filename: 'label.png', recordId: 'record-1', brandName: 'OLD TOM', status: 'pending', overallStatus: null, queueItemId: null, errorCode: null, errorMessage: null, retryable: false, durationMs: null }]
}

describe('batch API client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('creates a multipart manifest without setting Content-Type manually', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(detail), { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)
    const csv = new File(['record_id,filename\nrecord-1,label.png'], 'applications.csv', { type: 'text/csv' })
    const image = new File(['png'], 'label.png', { type: 'image/png' })

    await createBatch(csv, [image])

    const [, init] = fetchMock.mock.calls[0]!
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.headers['Content-Type']).toBeUndefined()
    const manifest = JSON.parse((init.body as FormData).get('images') as string)
    expect(manifest.images[0]).toEqual({ filename: 'label.png', mediaType: 'image/png', sizeBytes: 3 })
  })

  it('sends one matched image and optional mock scenario per process request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(detail), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const image = new File(['png'], 'label.png', { type: 'image/png' })

    await processBatchItem('batch-1', 'item-1', image, { mockScenario: 'success' })
    await skipBatchItem('batch-1', 'item-1')

    expect(fetchMock.mock.calls[0]![0]).toBe('/api/batches/batch-1/items/item-1/process')
    expect(fetchMock.mock.calls[0]![1].headers).toEqual({ 'X-OCR-Mock-Scenario': 'success' })
    expect(fetchMock.mock.calls[1]![0]).toBe('/api/batches/batch-1/items/item-1/skip')
  })

  it('preserves structured manifest validation errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: 'Correct the batch.', issues: [{ row: 2, field: 'filename', code: 'missing_image', message: 'No image matches.' }] }), { status: 422 })))
    const outcome = await createBatch(new File(['bad'], 'bad.csv'), [new File(['png'], 'label.png', { type: 'image/png' })])

    expect(outcome.kind).toBe('validation-error')
    if (outcome.kind === 'validation-error') expect(outcome.issues[0]?.code).toBe('missing_image')
  })
})
