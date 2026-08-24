import { useCallback, useEffect, useRef, useState } from 'react'

import {
  batchResultsUrl,
  createBatch,
  getBatch,
  processBatchItem,
  skipBatchItem
} from './api/batches'
import type { MockScenario } from './api/extractions'
import type { BatchDetail, BatchItemSummary } from './api/generated/verification'

type BatchFilter = 'all' | 'no_discrepancies_found' | 'review_needed' | 'analysis_incomplete' | 'processing' | 'failed'

const mockControlsEnabled = import.meta.env.VITE_ENABLE_OCR_MOCK_CONTROLS === 'true'
const mockScenarios: { value: MockScenario; label: string }[] = [
  { value: 'success', label: 'Successful extraction' },
  { value: 'warning_mismatch', label: 'Changed warning wording' },
  { value: 'warning_incomplete', label: 'Incomplete warning' },
  { value: 'not_label', label: 'Not a label image' },
  { value: 'uncertain_label', label: 'Uncertain label image' },
  { value: 'timeout', label: 'Timeout' },
  { value: 'provider_unavailable', label: 'Provider unavailable' }
]
const template = `record_id,filename,beverage_type,brand_name,class_type_designation,net_contents_value,net_contents_unit,alcohol_by_volume_percent,proof,producer_name,producer_city,producer_region,producer_country_code,imported,origin_country_code,origin_display_name
batch-record-1,label-1.png,distilled_spirits,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,750,mL,45,90,Example Distilling Company,Frankfort,KY,US,false,,
`
const templateUrl = `data:text/csv;charset=utf-8,${encodeURIComponent(template)}`

const itemStatusLabel: Record<BatchItemSummary['status'], string> = {
  pending: 'Waiting',
  processing: 'Processing',
  ready_for_review: 'Ready for human review',
  failed: 'Failed — batch paused',
  skipped: 'Skipped'
}
const automatedStatus = (item: BatchItemSummary) => {
  if (item.overallStatus === 'no_discrepancies_found') return 'No discrepancies found'
  if (item.overallStatus === 'review_needed') return 'Review needed'
  if (item.overallStatus === 'analysis_incomplete') return 'Review needed — analysis incomplete'
  return itemStatusLabel[item.status]
}

const validateFiles = (csvFile: File | null, images: File[]) => {
  const errors: string[] = []
  if (!csvFile) errors.push('Choose one CSV application file.')
  else if (!csvFile.name.toLowerCase().endsWith('.csv')) errors.push('The application manifest must be a CSV file.')
  else if (csvFile.size === 0) errors.push('The selected CSV file is empty.')
  else if (csvFile.size > 2_000_000) errors.push('The CSV file exceeds the 2 MB limit.')
  if (!images.length) errors.push('Choose at least one label image.')
  if (images.length > 200) errors.push('Choose no more than 200 label images.')
  const names = images.map((image) => image.name)
  for (const image of images) {
    if (!['image/jpeg', 'image/png'].includes(image.type)) errors.push(`${image.name} is not a JPEG or PNG image.`)
    else if (image.size === 0) errors.push(`${image.name} is empty.`)
    else if (image.size > 20_000_000) errors.push(`${image.name} exceeds the 20 MB limit.`)
  }
  for (const name of new Set(names.filter((candidate) => names.filter((value) => value === candidate).length > 1))) errors.push(`${name} was selected more than once.`)
  return errors
}

const matchesFilter = (item: BatchItemSummary, filter: BatchFilter) => {
  if (filter === 'all') return true
  if (filter === 'processing') return item.status === 'pending' || item.status === 'processing'
  if (filter === 'failed') return item.status === 'failed' || item.status === 'skipped'
  return item.overallStatus === filter
}

const batchNotice = (batch: BatchDetail) => {
  if (batch.status === 'paused') return 'Batch paused. Retry or skip every failed application to continue.'
  if (batch.status === 'completed') return 'Batch processing complete. Every application is ready for human review.'
  if (batch.status === 'completed_with_errors') return 'Batch processing complete with errors. Skipped applications were not added to the Reviewer Hub.'
  return 'Batch processing continues.'
}

export const BatchApplicationInput = ({ onOpenHub, onReviewNow }: { onOpenHub: () => void; onReviewNow: (queueItemId: string) => void }) => {
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [images, setImages] = useState<File[]>([])
  const [batch, setBatch] = useState<BatchDetail | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const [notice, setNotice] = useState('')
  const [filter, setFilter] = useState<BatchFilter>('all')
  const [mockScenario, setMockScenario] = useState<MockScenario>('success')
  const [submitting, setSubmitting] = useState(false)
  const errorRef = useRef<HTMLDivElement>(null)
  const schedulerRunning = useRef(false)
  useEffect(() => { if (errors.length) errorRef.current?.focus() }, [errors])

  const schedule = useCallback(async (initial: BatchDetail, availableImages: File[]) => {
    if (schedulerRunning.current) return
    schedulerRunning.current = true
    let current = initial
    try {
      while (current.status === 'processing') {
        const pending = current.items.filter((item) => item.status === 'pending').slice(0, 3)
        if (!pending.length) break
        setNotice(`Processing ${pending.length} application${pending.length === 1 ? '' : 's'}…`)
        await Promise.all(pending.map(async (item) => {
          const file = availableImages.find((candidate) => candidate.name === item.filename)
          if (!file) return
          const outcome = await processBatchItem(current.batchId, item.batchItemId, file, mockControlsEnabled ? { mockScenario } : {})
          if (outcome.kind === 'completed') setBatch(outcome.value)
        }))
        const refreshed = await getBatch(current.batchId)
        if (refreshed.kind !== 'completed') {
          setErrors([refreshed.message])
          break
        }
        current = refreshed.value
        setBatch(current)
      }
      setNotice(batchNotice(current))
    } finally {
      schedulerRunning.current = false
    }
  }, [mockScenario])

  const submit = async () => {
    const localErrors = validateFiles(csvFile, images)
    if (localErrors.length || !csvFile) {
      setErrors(localErrors)
      return
    }
    setSubmitting(true)
    setErrors([])
    setNotice('Validating the complete CSV and image manifest…')
    const outcome = await createBatch(csvFile, images)
    setSubmitting(false)
    if (outcome.kind !== 'completed') {
      const issueMessages = outcome.kind === 'validation-error'
        ? outcome.issues.map((issue) => `${issue.row ? `Row ${issue.row}: ` : ''}${issue.message}`)
        : [outcome.message]
      setErrors(issueMessages.length ? issueMessages : [outcome.message])
      setNotice('No applications were processed.')
      return
    }
    setBatch(outcome.value)
    setNotice('Batch validated. Processing has started.')
    void schedule(outcome.value, images)
  }

  const retry = async (item: BatchItemSummary, replacement?: File) => {
    if (!batch) return
    const file = replacement ?? images.find((candidate) => candidate.name === item.filename)
    if (!file || file.name !== item.filename) {
      setErrors([`Choose a replacement named exactly '${item.filename}'.`])
      return
    }
    if (!images.includes(file)) setImages((current) => [...current.filter((candidate) => candidate.name !== item.filename), file])
    setErrors([])
    const outcome = await processBatchItem(batch.batchId, item.batchItemId, file, mockControlsEnabled ? { mockScenario } : {})
    if (outcome.kind !== 'completed') { setErrors([outcome.message]); return }
    setBatch(outcome.value)
    setNotice(batchNotice(outcome.value))
    if (outcome.value.status === 'processing') void schedule(outcome.value, [...images.filter((candidate) => candidate.name !== item.filename), file])
  }

  const skip = async (item: BatchItemSummary) => {
    if (!batch) return
    const outcome = await skipBatchItem(batch.batchId, item.batchItemId)
    if (outcome.kind !== 'completed') { setErrors([outcome.message]); return }
    setBatch(outcome.value)
    setNotice(batchNotice(outcome.value))
    if (outcome.value.status === 'processing') void schedule(outcome.value, images)
  }

  const refresh = async () => {
    if (!batch) return
    const outcome = await getBatch(batch.batchId)
    if (outcome.kind !== 'completed') { setErrors([outcome.message]); return }
    setErrors([])
    setBatch(outcome.value)
    setNotice(batchNotice(outcome.value))
    if (outcome.value.status === 'processing') void schedule(outcome.value, images)
  }

  const reset = () => {
    setCsvFile(null); setImages([]); setBatch(null); setErrors([]); setNotice(''); setFilter('all')
  }
  const filtered = batch?.items.filter((item) => matchesFilter(item, filter)) ?? []
  const firstReady = batch?.items.find((item) => item.queueItemId)

  return <section className="batch-input" aria-labelledby="batch-title">
    <div className="section-heading"><div><p className="eyebrow">Bulk intake</p><h2 id="batch-title">Batch Application Input</h2></div>{batch && ['completed', 'completed_with_errors'].includes(batch.status) && <button type="button" className="secondary-button" onClick={reset}>Start another batch</button>}</div>
    <p>Upload a CSV and its matching label images. Each completed application is added to the temporary Reviewer Hub immediately.</p>
    <p className="session-notice">Batch data is held in server memory and resets when the backend restarts. Use only synthetic or public data.</p>
    {errors.length > 0 && <div className="error-summary" role="alert" tabIndex={-1} ref={errorRef}><h3>Correct these batch issues</h3><ul>{errors.map((error, index) => <li key={`${error}-${index}`}>{error}</li>)}</ul></div>}
    {!batch ? <div className="batch-setup">
      <div className="section-heading"><div><h3>1. Choose the application CSV</h3><p>The filename column connects each row to one selected image.</p></div><a className="button-link" href={templateUrl} download="batch-application-template.csv">Download CSV template</a></div>
      <label className="file-choice" htmlFor="batch-csv"><strong>CSV application file</strong><input id="batch-csv" type="file" accept=".csv,text/csv" onChange={(event) => setCsvFile(event.target.files?.[0] ?? null)} />{csvFile && <span>Selected: {csvFile.name}</span>}</label>
      <h3>2. Choose matching label images</h3>
      <p>Select up to 200 JPEG or PNG images. Filenames must match the CSV exactly.</p>
      <label className="drop-zone" htmlFor="batch-images" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); setImages(Array.from(event.dataTransfer.files)) }}><strong>Choose label images</strong><span>or drag and drop all matching files here</span><input className="visually-hidden" id="batch-images" type="file" multiple accept="image/jpeg,image/png" onChange={(event) => setImages(Array.from(event.target.files ?? []))} /></label>
      {images.length > 0 && <div className="selected-files"><h4>{images.length} images selected</h4><ul>{images.map((image, index) => <li key={`${image.name}-${index}`}>{image.name}</li>)}</ul></div>}
      {mockControlsEnabled && <label className="file-choice" htmlFor="batch-mock-scenario"><strong>Mock OCR scenario (development only)</strong><select id="batch-mock-scenario" value={mockScenario} onChange={(event) => setMockScenario(event.target.value as MockScenario)}>{mockScenarios.map((scenario) => <option key={scenario.value} value={scenario.value}>{scenario.label}</option>)}</select></label>}
      <div className="actions"><button type="button" disabled={submitting} onClick={() => void submit()}>{submitting ? 'Validating batch…' : 'Validate and process batch'}</button></div>
    </div> : <div className="batch-dashboard">
      <div className={`batch-summary batch-summary--${batch.status}`} aria-live="polite"><h3>{batch.status === 'completed' ? 'Batch processing complete' : batch.status === 'completed_with_errors' ? 'Batch processing complete with errors' : batch.status === 'paused' ? 'Batch processing paused' : 'Batch processing in progress'}</h3><p>{notice}</p><strong>Ready for human review: {batch.readyCount} of {batch.totalCount}</strong><progress aria-label="Applications ready for human review" max={batch.totalCount} value={batch.readyCount}>{batch.readyCount} of {batch.totalCount}</progress><dl><div><dt>Processed</dt><dd>{batch.processedCount}</dd></div><div><dt>Waiting</dt><dd>{batch.totalCount - batch.processedCount - batch.items.filter((item) => item.status === 'processing').length}</dd></div><div><dt>Failed</dt><dd>{batch.failedCount}</dd></div><div><dt>Skipped</dt><dd>{batch.skippedCount}</dd></div></dl></div>
      {batch.status === 'paused' && <div className="provider-notice"><strong>Resolve every failed application before processing continues.</strong><ul>{batch.items.filter((item) => item.status === 'failed').map((item) => <li key={item.batchItemId}>{item.brandName}: {item.errorMessage}</li>)}</ul></div>}
      <div className="batch-actions">{firstReady?.queueItemId && <button type="button" onClick={() => onReviewNow(firstReady.queueItemId!)}>Review first ready application</button>}<button type="button" className="secondary-button" onClick={onOpenHub}>Open Reviewer Hub</button><button type="button" className="secondary-button" onClick={() => void refresh()}>Refresh batch status</button><a className="button-link" href={batchResultsUrl(batch.batchId)} download>Download results CSV</a></div>
      <label className="batch-filter" htmlFor="batch-filter">Show<select id="batch-filter" value={filter} onChange={(event) => setFilter(event.target.value as BatchFilter)}><option value="all">All applications</option><option value="no_discrepancies_found">No discrepancies</option><option value="review_needed">Review needed</option><option value="analysis_incomplete">Analysis incomplete</option><option value="processing">Waiting or processing</option><option value="failed">Failed or skipped</option></select></label>
      <ul className="batch-results">{filtered.map((item) => <li className={`batch-result batch-result--${item.overallStatus ?? item.status}`} key={item.batchItemId}><div><span>CSV row {item.rowNumber}</span><strong>{item.brandName}</strong><small>{item.recordId} · {item.filename}</small></div><div><strong>{automatedStatus(item)}</strong>{item.durationMs != null && <small>{(item.durationMs / 1000).toFixed(1)} seconds</small>}{item.errorMessage && <small>{item.errorMessage}</small>}</div><div className="batch-result-actions">{item.queueItemId && <button type="button" onClick={() => onReviewNow(item.queueItemId!)}>Review now</button>}{item.status === 'failed' && <><button type="button" onClick={() => void retry(item)}>Retry</button><label className="button-link replacement-control">Choose replacement<input className="visually-hidden" type="file" accept="image/jpeg,image/png" onChange={(event) => { const replacement = event.target.files?.[0]; if (replacement) void retry(item, replacement) }} /></label><button type="button" className="secondary-button" onClick={() => void skip(item)}>Skip and continue</button></>}</div></li>)}</ul>
      {filtered.length === 0 && <p>No applications match this filter.</p>}
    </div>}
  </section>
}
