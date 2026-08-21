import type {
  ComparisonRequest,
  OcrExtractionResult,
  VerificationResult,
  VerificationSubmission
} from './generated/verification'

export type ComparisonApiOutcome =
  | { kind: 'completed'; result: VerificationResult }
  | { kind: 'validation-error'; message: string }
  | { kind: 'network-error'; message: string }

const isVerificationResult = (value: unknown): value is VerificationResult => {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return typeof candidate.verificationId === 'string' &&
    typeof candidate.submissionId === 'string' &&
    typeof candidate.overallStatus === 'string' &&
    Array.isArray(candidate.findings) &&
    typeof candidate.ruleset === 'object' && candidate.ruleset !== null
}

export const requestComparison = async (
  submission: VerificationSubmission,
  extraction: OcrExtractionResult,
  options: { fetchImplementation?: typeof fetch } = {}
): Promise<ComparisonApiOutcome> => {
  const payload: ComparisonRequest = {
    comparisonId: `comparison-${crypto.randomUUID()}`,
    submission,
    extraction
  }
  try {
    const response = await (options.fetchImplementation ?? fetch)('/api/comparisons', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(payload)
    })
    const body: unknown = await response.json().catch(() => null)
    if (response.status === 200 && isVerificationResult(body)) return { kind: 'completed', result: body }
    if (response.status === 422) return { kind: 'validation-error', message: 'The comparison request could not be validated. Try the review again.' }
    return { kind: 'network-error', message: 'The comparison service returned an unexpected response. Try again.' }
  } catch {
    return { kind: 'network-error', message: 'The comparison service could not be reached. Try again.' }
  }
}
