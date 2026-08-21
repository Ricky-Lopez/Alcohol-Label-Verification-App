import { useCallback, useEffect, useRef, useState } from 'react'

import {
  getReviewQueue,
  getReviewQueueItem,
  submitHumanReview,
  undoHumanReview,
  type QueueApiOutcome
} from './api/reviewQueue'
import type {
  HumanReviewDecision,
  HumanReviewReceipt,
  ReviewQueueItemDetail,
  ReviewQueueItemSummary,
  ReviewQueueResponse,
  VerificationField
} from './api/generated/verification'

const statusLabel: Record<ReviewQueueItemSummary['overallStatus'], string> = {
  no_discrepancies_found: 'No discrepancies found',
  review_needed: 'Review needed',
  analysis_incomplete: 'Review needed'
}

const needsIncompleteAnalysisBadge = (status: ReviewQueueItemSummary['overallStatus']) => status === 'analysis_incomplete'

const fieldLabel: Record<VerificationField, string> = {
  brand_name: 'Brand name', class_type_designation: 'Class/type designation', alcohol_content: 'Alcohol content', net_contents: 'Net contents', responsible_party_name: 'Bottler/producer name', responsible_party_address: 'Bottler/producer address', country_of_origin: 'Country of origin', appellation_of_origin: 'Appellation of origin', government_warning_text: 'Government warning text', government_warning_heading_case: 'Warning heading capitalization', government_warning_heading_weight: 'Warning heading weight', government_warning_prominence: 'Warning prominence', government_warning_placement: 'Warning placement', government_warning_type_size: 'Warning type size', same_field_of_vision: 'Same field of vision', general_legibility: 'General legibility', additional_required_statement: 'Additional required statement'
}

const isEditableTarget = (target: EventTarget | null) => target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))

export const ReviewerHub = ({ onHome }: { onHome: () => void }) => {
  const [queue, setQueue] = useState<ReviewQueueResponse | null>(null)
  const [detail, setDetail] = useState<ReviewQueueItemDetail | null>(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'all' | 'no_discrepancies_found' | 'review_needed'>('all')
  const [comment, setComment] = useState('')
  const [notice, setNotice] = useState('')
  const [receipt, setReceipt] = useState<HumanReviewReceipt | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const detailHeading = useRef<HTMLHeadingElement>(null)

  const refresh = useCallback(async () => {
    const outcome = await getReviewQueue()
    if (outcome.kind === 'completed') { setQueue(outcome.value); setError(null); return outcome.value }
    setError(outcome.message); return null
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => { if (detail) detailHeading.current?.focus() }, [detail])

  const filtered = (queue?.items ?? []).filter((item) => (filter === 'all' || item.overallStatus === filter || (filter === 'review_needed' && item.overallStatus === 'analysis_incomplete')) && `${item.brandName} ${item.recordId}`.toLowerCase().includes(search.trim().toLowerCase()))
  const select = async (item: ReviewQueueItemSummary) => {
    setBusy(true)
    const outcome = await getReviewQueueItem(item.queueItemId)
    setBusy(false)
    if (outcome.kind === 'completed') { setDetail(outcome.value); setComment(''); setError(null) } else setError(outcome.message)
  }
  const move = async (direction: -1 | 1) => {
    if (!detail) return
    const index = (queue?.items ?? []).findIndex((item) => item.queueItemId === detail.summary.queueItemId)
    const next = queue?.items[index + direction]
    if (next) await select(next)
  }
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!detail || isEditableTarget(event.target)) return
      if (event.key === 'ArrowLeft') { event.preventDefault(); void move(-1) }
      if (event.key === 'ArrowRight') { event.preventDefault(); void move(1) }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [detail, queue])

  const decide = async (decision: HumanReviewDecision) => {
    if (!detail) return
    const currentId = detail.summary.queueItemId
    const currentIndex = (queue?.items ?? []).findIndex((item) => item.queueItemId === currentId)
    setBusy(true)
    const outcome = await submitHumanReview(currentId, decision, comment)
    if (outcome.kind !== 'completed') { setBusy(false); setError(outcome.message); return }
    setReceipt(outcome.value)
    setNotice(`Application ${decision === 'approved' ? 'approved' : 'rejected'}. ${outcome.value.remainingCount} items remain. You can undo for 10 seconds.`)
    const updated = await refresh()
    const next = updated?.items[currentIndex] ?? updated?.items[currentIndex - 1]
    if (next) await select(next); else setDetail(null)
    setBusy(false)
  }
  const undo = async () => {
    if (!receipt) return
    setBusy(true)
    const outcome = await undoHumanReview(receipt.decisionId)
    setBusy(false)
    if (outcome.kind === 'completed') { await refresh(); setDetail(outcome.value); setReceipt(null); setNotice('The application was restored to its original queue position.') } else setError(outcome.message)
  }

  if (!detail) return <section className="reviewer-hub" aria-labelledby="hub-title"><div className="section-heading"><div><p className="eyebrow">Primary workflow</p><h2 id="hub-title">Reviewer Hub</h2></div><button type="button" className="secondary-button" onClick={onHome}>Return home</button></div><p className="session-notice">This is a temporary, single-reviewer queue. It resets when the backend restarts.</p><p aria-live="polite">{notice}</p>{error && <div className="error-summary" role="alert"><p>{error}</p><button type="button" onClick={() => void refresh()}>Retry queue</button></div>}<div className="queue-controls"><label>Search applications<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Brand or record ID" /></label><label>Show<select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}><option value="all">All applications</option><option value="no_discrepancies_found">No discrepancies</option><option value="review_needed">Review needed</option></select></label></div><h3>{queue ? `${queue.totalCount} applications in queue` : 'Loading queue…'}</h3>{queue?.items.length === 0 ? <div className="empty-state"><h3>Queue complete</h3><p>Every active application has received a human decision.</p><button type="button" onClick={onHome}>Return home</button></div> : <ul className="queue-list">{filtered.map((item) => <li key={item.queueItemId}><button type="button" className={`queue-item queue-item--${item.overallStatus === 'no_discrepancies_found' ? item.overallStatus : 'review_needed'}`} disabled={busy} onClick={() => void select(item)}><span>#{item.position}</span><strong>{item.brandName}</strong><span>{item.beverageType}</span><span>{statusLabel[item.overallStatus]}</span><span>{item.attentionCount} attention items</span><small>{item.recordId} · queued {new Date(item.queuedAt).toLocaleString()}</small></button></li>)}</ul>}{queue && filtered.length === 0 && <p>No active applications match the current filter.</p>}</section>

  const verification = detail.verification
  return <section className="review-workspace" aria-labelledby="review-title"><p className="session-notice">Temporary queue: decisions and comments reset when the backend restarts.</p><p className="shortcut-hint">Use ← and → to move through applications when you are not editing the optional comment.</p><div className="review-header"><button type="button" className="secondary-button" onClick={() => setDetail(null)}>Back to queue</button><div><p className="eyebrow">Application #{detail.summary.position}</p><h2 id="review-title" ref={detailHeading} tabIndex={-1}>{detail.application.expectedLabel.brandName}</h2><p>{statusLabel[verification.overallStatus]} · {detail.summary.recordId}</p>{needsIncompleteAnalysisBadge(verification.overallStatus) && <p className="analysis-badge">Analysis incomplete: some requirements could not be evaluated automatically.</p>}</div><div className="review-navigation"><button type="button" className="secondary-button" disabled={busy || !queue?.items.findIndex((item) => item.queueItemId === detail.summary.queueItemId)} onClick={() => void move(-1)}>← Previous</button><button type="button" className="secondary-button" disabled={busy || (queue?.items.findIndex((item) => item.queueItemId === detail.summary.queueItemId) ?? -1) === (queue?.items.length ?? 1) - 1} onClick={() => void move(1)}>Next →</button></div></div><div className="review-grid"><figure className="label-evidence"><img src={detail.images[0]?.imageUrl} alt={detail.images[0]?.altText} /><figcaption>Submitted label image · {detail.images[0]?.panelType} panel</figcaption></figure><section><h3>Application values</h3><dl className="application-summary"><div><dt>Class/type</dt><dd>{detail.application.expectedLabel.classTypeDesignation}</dd></div><div><dt>Net contents</dt><dd>{detail.application.expectedLabel.netContents.value} {detail.application.expectedLabel.netContents.unit}</dd></div><div><dt>Alcohol content</dt><dd>{detail.application.expectedLabel.alcoholContent?.abvPercent ?? 'Not applicable'}% ABV</dd></div><div><dt>Bottler/producer</dt><dd>{detail.application.expectedLabel.responsibleParties.map((party) => party.name).join(', ')}</dd></div></dl></section></div><section className="verification-findings"><h3>Comparison findings</h3><p className="result-disclaimer">Automated findings are decision support only. Your approval or rejection is the human review decision.</p>{verification.findings.map((finding, index) => <article className={`finding finding--${finding.severity}`} key={`${finding.ruleId}-${index}`}><h4>{fieldLabel[finding.field]}: {finding.outcome.replaceAll('_', ' ')}</h4><p>{finding.explanation}</p>{finding.expected && <p><strong>Expected:</strong> {finding.expected.displayValue}</p>}{finding.detected?.length ? <p><strong>Detected:</strong> {finding.detected.map((value) => value.displayValue).join(' | ')}</p> : null}</article>)}</section><label className="review-comment">Optional reviewer comment<textarea value={comment} onChange={(event) => setComment(event.target.value)} maxLength={2000} placeholder="Add context for the human decision, if helpful." /></label><div className="review-actions"><button type="button" className="approve-button" disabled={busy} onClick={() => void decide('approved')}>Approve application</button><button type="button" className="reject-button" disabled={busy} onClick={() => void decide('rejected')}>Reject application</button></div><div aria-live="polite">{notice}</div>{receipt && <button type="button" className="secondary-button" disabled={busy} onClick={() => void undo()}>Undo decision</button>}{error && <div className="error-summary" role="alert"><p>{error}</p></div>}</section>
}
