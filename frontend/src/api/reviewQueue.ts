import type {
  HumanReviewDecision,
  HumanReviewReceipt,
  ReviewQueueItemDetail,
  ReviewQueueResponse
} from './generated/verification'

export type QueueApiOutcome<T> =
  | { kind: 'completed'; value: T }
  | { kind: 'conflict'; message: string }
  | { kind: 'not-found'; message: string }
  | { kind: 'network-error'; message: string }

const request = async <T>(path: string, init?: RequestInit): Promise<QueueApiOutcome<T>> => {
  try {
    const response = await fetch(path, { headers: { Accept: 'application/json', ...init?.headers }, ...init })
    const body: unknown = await response.json().catch(() => null)
    if (response.ok) return { kind: 'completed', value: body as T }
    if (response.status === 409) return { kind: 'conflict', message: 'The queue changed. Refresh and choose another item.' }
    if (response.status === 404) return { kind: 'not-found', message: 'That queue item is no longer available.' }
    return { kind: 'network-error', message: 'The reviewer queue returned an unexpected response.' }
  } catch {
    return { kind: 'network-error', message: 'The reviewer queue could not be reached.' }
  }
}

export const getReviewQueue = () => request<ReviewQueueResponse>('/api/review-queue')
export const getReviewQueueItem = (queueItemId: string) => request<ReviewQueueItemDetail>(`/api/review-queue/${queueItemId}`)
export const submitHumanReview = (queueItemId: string, decision: HumanReviewDecision, comment: string) => request<HumanReviewReceipt>(`/api/review-queue/${queueItemId}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, ...(comment.trim() ? { comment: comment.trim() } : {}) }) })
export const undoHumanReview = (decisionId: string) => request<ReviewQueueItemDetail>(`/api/review-queue/decisions/${decisionId}/undo`, { method: 'POST' })
