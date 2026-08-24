import type {
  BatchDetail,
  BatchImageDeclaration,
  BatchValidationIssue,
  BatchValidationResponse
} from './generated/verification'
import type { MockScenario } from './extractions'

export type BatchApiOutcome =
  | { kind: 'completed'; value: BatchDetail }
  | { kind: 'validation-error'; message: string; issues: BatchValidationIssue[] }
  | { kind: 'conflict'; message: string }
  | { kind: 'not-found'; message: string }
  | { kind: 'network-error'; message: string }

const isBatchDetail = (body: unknown): body is BatchDetail => {
  if (!body || typeof body !== 'object') return false
  const candidate = body as Partial<BatchDetail>
  return typeof candidate.batchId === 'string' && Array.isArray(candidate.items)
}

const messageFrom = (body: unknown, fallback: string) => {
  if (!body || typeof body !== 'object') return fallback
  const detail = (body as { detail?: unknown }).detail
  return typeof detail === 'string' ? detail : fallback
}

const request = async (path: string, init?: RequestInit): Promise<BatchApiOutcome> => {
  try {
    const response = await fetch(path, {
      headers: { Accept: 'application/json', ...init?.headers },
      ...init
    })
    const body: unknown = await response.json().catch(() => null)
    if (isBatchDetail(body)) return { kind: 'completed', value: body }
    if (response.status === 422) {
      const validation = body as Partial<BatchValidationResponse> | null
      return {
        kind: 'validation-error',
        message: validation?.message ?? messageFrom(body, 'Correct the batch information and try again.'),
        issues: validation?.issues ?? []
      }
    }
    if (response.status === 409) return { kind: 'conflict', message: messageFrom(body, 'The batch is paused or changed. Refresh its status.') }
    if (response.status === 404) return { kind: 'not-found', message: 'That temporary batch is no longer available.' }
    return { kind: 'network-error', message: 'The batch service returned an unexpected response.' }
  } catch {
    return { kind: 'network-error', message: 'The batch service could not be reached.' }
  }
}

export const createBatch = (csvFile: File, images: File[]) => {
  const declarations: BatchImageDeclaration[] = images.map((image) => ({
    filename: image.name,
    mediaType: image.type as BatchImageDeclaration['mediaType'],
    sizeBytes: image.size
  }))
  const body = new FormData()
  body.append('applications', csvFile, csvFile.name)
  body.append('images', JSON.stringify({ images: declarations }))
  return request('/api/batches', { method: 'POST', body })
}

export const getBatch = (batchId: string) => request(`/api/batches/${batchId}`)

export const processBatchItem = (
  batchId: string,
  itemId: string,
  image: File,
  options: { mockScenario?: MockScenario } = {}
) => {
  const body = new FormData()
  body.append('image', image, image.name)
  const headers = options.mockScenario
    ? { 'X-OCR-Mock-Scenario': options.mockScenario }
    : undefined
  return request(`/api/batches/${batchId}/items/${itemId}/process`, {
    method: 'POST',
    headers,
    body
  })
}

export const skipBatchItem = (batchId: string, itemId: string) =>
  request(`/api/batches/${batchId}/items/${itemId}/skip`, { method: 'POST' })

export const batchResultsUrl = (batchId: string) => `/api/batches/${batchId}/results.csv`
