import type {
  LabelImageInput,
  OcrExtractionResult,
  VerificationSubmission
} from './generated/verification'

export interface PendingLabelImage {
  file: File
  metadata: LabelImageInput
  previewUrl: string
}

export type ExtractionApiOutcome =
  | { kind: 'completed'; httpStatus: 200; result: OcrExtractionResult }
  | {
      kind: 'provider-failure'
      httpStatus: 502 | 503 | 504
      result: OcrExtractionResult
    }
  | { kind: 'validation-error'; httpStatus: 422; message: string }
  | { kind: 'network-error'; message: string }

export type MockScenario =
  | 'success'
  | 'warning_mismatch'
  | 'warning_incomplete'
  | 'not_label'
  | 'uncertain_label'
  | 'timeout'
  | 'provider_unavailable'

const REQUEST_TIMEOUT_MS = 10_000

const isExtractionResult = (value: unknown): value is OcrExtractionResult => {
  if (typeof value !== 'object' || value === null) {
    return false
  }

  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.extractionId === 'string' &&
    typeof candidate.submissionId === 'string' &&
    typeof candidate.status === 'string' &&
    Array.isArray(candidate.fieldCandidates) &&
    Array.isArray(candidate.issues)
  )
}

const validationMessage = (body: unknown): string => {
  if (typeof body === 'object' && body !== null) {
    const detail = (body as Record<string, unknown>).detail
    if (typeof detail === 'string') {
      return detail
    }
  }
  return 'The submitted information could not be validated. Review the fields and try again.'
}

export const requestExtraction = async (
  submission: VerificationSubmission,
  image: PendingLabelImage,
  options: { mockScenario?: MockScenario; fetchImplementation?: typeof fetch } = {}
): Promise<ExtractionApiOutcome> => {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  const formData = new FormData()
  formData.append('submission', JSON.stringify(submission))
  formData.append('images', image.file, image.metadata.fileName)

  const headers: HeadersInit = {}
  if (options.mockScenario) {
    headers['X-OCR-Mock-Scenario'] = options.mockScenario
  }

  try {
    const response = await (options.fetchImplementation ?? fetch)('/api/extractions', {
      method: 'POST',
      headers,
      body: formData,
      signal: controller.signal
    })
    const body: unknown = await response.json().catch(() => null)

    if (response.status === 200 && isExtractionResult(body)) {
      return { kind: 'completed', httpStatus: 200, result: body }
    }
    if (
      (response.status === 502 || response.status === 503 || response.status === 504) &&
      isExtractionResult(body)
    ) {
      return { kind: 'provider-failure', httpStatus: response.status, result: body }
    }
    if (response.status === 422) {
      return { kind: 'validation-error', httpStatus: 422, message: validationMessage(body) }
    }
    return {
      kind: 'network-error',
      message: 'The verification service returned an unexpected response. Try again.'
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return {
        kind: 'network-error',
        message: 'The request took too long. Check the service and try again.'
      }
    }
    return {
      kind: 'network-error',
      message: 'The verification service could not be reached. Check the service and try again.'
    }
  } finally {
    window.clearTimeout(timeoutId)
  }
}
