import { useCallback, useEffect, useReducer, useRef, useState } from 'react'

import {
  requestExtraction,
  type ExtractionApiOutcome,
  type MockScenario,
  type PendingLabelImage
} from './api/extractions'
import { requestComparison, type ComparisonApiOutcome } from './api/comparisons'
import { ReviewerHub } from './ReviewerHub'
import type {
  ApplicationRecord,
  BeverageType,
  LabelPanelType,
  NetContentsUnit,
  OcrExtractionResult,
  VerificationResult,
  VerificationField,
  VerificationSubmission
} from './api/generated/verification'
import { exampleApplication } from './exampleApplication'

type ReviewStep = 'expected-values' | 'upload-label' | 'review-extraction'

type FormValues = {
  beverageType: BeverageType
  brandName: string
  classTypeDesignation: string
  netContentsValue: string
  netContentsUnit: NetContentsUnit
  abvPercent: string
  proof: string
  responsiblePartyName: string
  city: string
  region: string
  countryCode: string
  imported: boolean
  originCountryCode: string
  originDisplayName: string
}

type WorkflowState = {
  step: ReviewStep
  values: FormValues
  image: PendingLabelImage | null
  errors: Record<string, string>
  outcome: ExtractionApiOutcome | null
  submission: VerificationSubmission | null
  comparison: ComparisonApiOutcome | null
  isSubmitting: boolean
  mockScenario: MockScenario
}

type WorkflowAction =
  | { type: 'update-value'; field: keyof FormValues; value: string | boolean }
  | { type: 'set-image'; image: PendingLabelImage | null }
  | { type: 'set-panel'; panelType: LabelPanelType }
  | { type: 'set-errors'; errors: Record<string, string> }
  | { type: 'set-step'; step: ReviewStep }
  | { type: 'set-outcome'; outcome: ExtractionApiOutcome | null }
  | { type: 'set-submission'; submission: VerificationSubmission | null }
  | { type: 'set-comparison'; comparison: ComparisonApiOutcome | null }
  | { type: 'set-submitting'; isSubmitting: boolean }
  | { type: 'set-mock-scenario'; scenario: MockScenario }
  | { type: 'load-example' }
  | { type: 'start-new' }

const blankValues = (): FormValues => ({
  beverageType: 'distilled_spirits', brandName: '', classTypeDesignation: '', netContentsValue: '', netContentsUnit: 'mL', abvPercent: '', proof: '', responsiblePartyName: '', city: '', region: '', countryCode: 'US', imported: false, originCountryCode: '', originDisplayName: ''
})

const initialState = (): WorkflowState => ({ step: 'expected-values', values: blankValues(), image: null, errors: {}, outcome: null, submission: null, comparison: null, isSubmitting: false, mockScenario: 'success' })

const valuesFromExample = (): FormValues => {
  const expected = exampleApplication.expectedLabel
  const party = expected.responsibleParties[0]
  return { beverageType: exampleApplication.beverageType, brandName: expected.brandName, classTypeDesignation: expected.classTypeDesignation, netContentsValue: String(expected.netContents.value), netContentsUnit: expected.netContents.unit, abvPercent: String(expected.alcoholContent?.abvPercent ?? ''), proof: String(expected.alcoholContent?.proof ?? ''), responsiblePartyName: party.name, city: party.address.city, region: party.address.region ?? '', countryCode: party.address.countryCode, imported: exampleApplication.imported, originCountryCode: expected.countryOfOrigin?.countryCode ?? '', originDisplayName: expected.countryOfOrigin?.displayName ?? '' }
}

const workflowReducer = (state: WorkflowState, action: WorkflowAction): WorkflowState => {
  switch (action.type) {
    case 'update-value': return { ...state, values: { ...state.values, [action.field]: action.value }, errors: { ...state.errors, [action.field]: '' } }
    case 'set-image': return { ...state, image: action.image, errors: { ...state.errors, image: '' } }
    case 'set-panel': return state.image ? { ...state, image: { ...state.image, metadata: { ...state.image.metadata, panelType: action.panelType } } } : state
    case 'set-errors': return { ...state, errors: action.errors }
    case 'set-step': return { ...state, step: action.step, errors: {} }
    case 'set-outcome': return { ...state, outcome: action.outcome }
    case 'set-submission': return { ...state, submission: action.submission }
    case 'set-comparison': return { ...state, comparison: action.comparison }
    case 'set-submitting': return { ...state, isSubmitting: action.isSubmitting }
    case 'set-mock-scenario': return { ...state, mockScenario: action.scenario }
    case 'load-example': return { ...state, values: valuesFromExample(), errors: {} }
    case 'start-new': return initialState()
  }
}

const fieldLabels: Record<VerificationField, string> = {
  brand_name: 'Brand name', class_type_designation: 'Class/type designation', alcohol_content: 'Alcohol content', net_contents: 'Net contents', responsible_party_name: 'Responsible party name', responsible_party_address: 'Responsible party address', country_of_origin: 'Country of origin', appellation_of_origin: 'Appellation of origin', government_warning_text: 'Government warning text', government_warning_heading_case: 'Government warning heading capitalization', government_warning_heading_weight: 'Government warning heading weight', government_warning_prominence: 'Government warning prominence', government_warning_placement: 'Government warning placement', government_warning_type_size: 'Government warning type size', same_field_of_vision: 'Same field of vision', general_legibility: 'General legibility', additional_required_statement: 'Additional required statement'
}

const mockScenarios: { value: MockScenario; label: string }[] = [
  { value: 'success', label: 'Successful extraction' }, { value: 'warning_mismatch', label: 'Changed warning wording' }, { value: 'warning_incomplete', label: 'Incomplete warning' }, { value: 'not_label', label: 'Not a label image' }, { value: 'uncertain_label', label: 'Uncertain label image' }, { value: 'timeout', label: 'Timeout' }, { value: 'provider_unavailable', label: 'Provider unavailable' }
]
const mockControlsEnabled = import.meta.env.VITE_ENABLE_OCR_MOCK_CONTROLS === 'true'
const errorId = (field: string) => `${field}-error`
const fieldExamples: Record<string, string> = {
  beverageType: 'Example: Distilled spirits',
  netContentsValue: 'Example: 750',
  netContentsUnit: 'Example: mL',
  abvPercent: 'Example: 45',
  proof: 'Example: 90',
  responsiblePartyName: 'Example: Example Distilling Company',
  city: 'Example: Frankfort',
  region: 'Example: KY',
  countryCode: 'Example: US',
  originCountryCode: 'Example: FR',
  originDisplayName: 'Example: France',
  panelType: 'Example: Brand panel',
  mockScenario: 'Example: Successful extraction'
}
const formatBytes = (bytes: number) => `${(bytes / 1_000_000).toFixed(bytes >= 1_000_000 ? 1 : 2)} MB`
const resultHeading = (result: OcrExtractionResult) => result.status === 'succeeded' ? 'Extraction complete' : result.status === 'partial' ? 'Extraction partially complete' : 'Extraction failed'

const validateExpectedValues = (values: FormValues): Record<string, string> => {
  const errors: Record<string, string> = {}
  const required = (field: keyof FormValues, label: string) => { if (!String(values[field]).trim()) errors[field] = `${label} is required.` }
  required('brandName', 'Brand name'); required('classTypeDesignation', 'Class/type designation'); required('netContentsValue', 'Net contents'); required('responsiblePartyName', 'Responsible business name'); required('city', 'City')
  if (Number(values.netContentsValue) <= 0) errors.netContentsValue = 'Net contents must be greater than zero.'
  if (values.beverageType === 'distilled_spirits') { required('abvPercent', 'Alcohol by volume'); if (Number(values.abvPercent) < 0 || Number(values.abvPercent) > 100) errors.abvPercent = 'Alcohol by volume must be between 0 and 100.' }
  if (values.proof && (Number(values.proof) < 0 || Number(values.proof) > 200)) errors.proof = 'Proof must be between 0 and 200.'
  if (!/^[A-Za-z]{2}$/.test(values.countryCode)) errors.countryCode = 'Use a two-letter country code, such as US.'
  if (values.imported) { if (!/^[A-Za-z]{2}$/.test(values.originCountryCode)) errors.originCountryCode = 'Use a two-letter country code, such as FR.'; required('originDisplayName', 'Country of origin') }
  return errors
}

export const buildSubmission = (values: FormValues, image: PendingLabelImage): VerificationSubmission => {
  const alcoholContent = values.beverageType === 'distilled_spirits' || values.abvPercent ? { abvPercent: Number(values.abvPercent), ...(values.proof ? { proof: Number(values.proof) } : {}) } : null
  const application: ApplicationRecord = {
    schemaVersion: '1.0', recordId: `ad-hoc-${crypto.randomUUID()}`, intakeSource: 'ad_hoc', beverageType: values.beverageType, imported: values.imported,
    expectedLabel: {
      brandName: values.brandName.trim(), classTypeDesignation: values.classTypeDesignation.trim(), alcoholContent,
      netContents: { value: Number(values.netContentsValue), unit: values.netContentsUnit },
      responsibleParties: [{ name: values.responsiblePartyName.trim(), address: { streetLines: [], city: values.city.trim(), ...(values.region.trim() ? { region: values.region.trim() } : {}), countryCode: values.countryCode.trim().toUpperCase() } }],
      countryOfOrigin: values.imported ? { countryCode: values.originCountryCode.trim().toUpperCase(), displayName: values.originDisplayName.trim() } : null,
      appellationOfOrigin: null, additionalRequiredStatements: []
    }
  }
  return { submissionId: `submission-${crypto.randomUUID()}`, application, images: [image.metadata] }
}

const ApplicationInput = () => {
  const [state, dispatch] = useReducer(workflowReducer, undefined, initialState)
  const [serviceState, setServiceState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [serviceMessage, setServiceMessage] = useState('Checking verification service…')
  const errorSummaryRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const checkService = useCallback(async () => { setServiceState('loading'); setServiceMessage('Checking verification service…'); try { const response = await fetch('/health', { headers: { Accept: 'application/json' } }); if (!response.ok) throw new Error('Unavailable'); setServiceState('ready'); setServiceMessage('Verification service is available.') } catch { setServiceState('error'); setServiceMessage('The verification service is unavailable. Start the API and try again.') } }, [])
  useEffect(() => { void checkService() }, [checkService])
  useEffect(() => () => { if (state.image) URL.revokeObjectURL(state.image.previewUrl) }, [state.image])
  useEffect(() => { if (Object.values(state.errors).some(Boolean)) errorSummaryRef.current?.focus() }, [state.errors])
  const updateValue = (field: keyof FormValues, value: string | boolean) => dispatch({ type: 'update-value', field, value })
  const selectImage = (file: File | undefined) => {
    if (!file) return
    const errors: Record<string, string> = {}
    if (!['image/jpeg', 'image/png'].includes(file.type)) errors.image = 'Choose a JPEG or PNG image.'
    else if (file.size === 0) errors.image = 'The selected image is empty. Choose another file.'
    else if (file.size > 20_000_000) errors.image = 'The selected image exceeds the 20 MB limit.'
    if (Object.keys(errors).length) { dispatch({ type: 'set-errors', errors }); return }
    if (state.image) URL.revokeObjectURL(state.image.previewUrl)
    dispatch({ type: 'set-image', image: { file, previewUrl: URL.createObjectURL(file), metadata: { clientImageId: `image-${crypto.randomUUID()}`, fileName: file.name, mediaType: file.type as 'image/jpeg' | 'image/png', sizeBytes: file.size, panelType: 'unknown' } } })
  }
  const goToUpload = () => { const errors = validateExpectedValues(state.values); if (Object.keys(errors).length) { dispatch({ type: 'set-errors', errors }); return }; dispatch({ type: 'set-step', step: 'upload-label' }) }
  const submit = async () => {
    const errors = validateExpectedValues(state.values); if (!state.image) errors.image = 'Upload one label image before verifying.'
    if (Object.keys(errors).length) { dispatch({ type: 'set-errors', errors }); dispatch({ type: 'set-step', step: state.image ? 'expected-values' : 'upload-label' }); return }
    if (!state.image) return
    const submission = buildSubmission(state.values, state.image)
    dispatch({ type: 'set-submitting', isSubmitting: true }); dispatch({ type: 'set-outcome', outcome: null }); dispatch({ type: 'set-comparison', comparison: null }); dispatch({ type: 'set-submission', submission })
    const outcome = await requestExtraction(submission, state.image, mockControlsEnabled ? { mockScenario: state.mockScenario } : {})
    dispatch({ type: 'set-submitting', isSubmitting: false }); dispatch({ type: 'set-outcome', outcome })
    if (outcome.kind === 'validation-error') { dispatch({ type: 'set-errors', errors: { image: outcome.message } }); dispatch({ type: 'set-step', step: 'upload-label' }); return }
    if (outcome.kind === 'completed') dispatch({ type: 'set-comparison', comparison: await requestComparison(submission, outcome.result) })
    dispatch({ type: 'set-step', step: 'review-extraction' })
  }
  const retryComparison = async () => {
    if (!state.submission || state.outcome?.kind !== 'completed') return
    dispatch({ type: 'set-submitting', isSubmitting: true })
    dispatch({ type: 'set-comparison', comparison: await requestComparison(state.submission, state.outcome.result) })
    dispatch({ type: 'set-submitting', isSubmitting: false })
  }
  const startNew = () => { if (state.image) URL.revokeObjectURL(state.image.previewUrl); dispatch({ type: 'start-new' }); if (fileInputRef.current) fileInputRef.current.value = '' }
  const removeImage = () => { if (state.image) URL.revokeObjectURL(state.image.previewUrl); dispatch({ type: 'set-image', image: null }); if (fileInputRef.current) fileInputRef.current.value = '' }
  const currentStepIndex = ['expected-values', 'upload-label', 'review-extraction'].indexOf(state.step)
  return <main className="app-shell">
    <header className="app-header"><p className="eyebrow">Decision-support prototype</p><h1>Alcohol Label Verification</h1><p className="lede">Review one synthetic or public label at a time. Results assist review and are not a final compliance determination.</p></header>
    <section className={`service-banner service-banner--${serviceState}`} aria-live="polite"><p>{serviceMessage}</p>{serviceState === 'error' && <button type="button" className="secondary-button" onClick={() => void checkService()}>Try again</button>}</section>
    <ol className="step-list" aria-label="Review steps">{['Expected values', 'Upload label', 'Review results'].map((label, index) => <li key={label} aria-current={index === currentStepIndex ? 'step' : undefined} className={index <= currentStepIndex ? 'step--active' : ''}><span>{index + 1}</span>{label}</li>)}</ol>
    {Object.values(state.errors).some(Boolean) && <div className="error-summary" role="alert" tabIndex={-1} ref={errorSummaryRef}><h2>Review the highlighted information</h2><ul>{Object.entries(state.errors).filter(([, message]) => message).map(([field, message]) => <li key={field}><a href={`#${field}`}>{message}</a></li>)}</ul></div>}
    {state.step === 'expected-values' && <ExpectedValues values={state.values} errors={state.errors} updateValue={updateValue} loadExample={() => dispatch({ type: 'load-example' })} onContinue={goToUpload} />}
    {state.step === 'upload-label' && <UploadLabel image={state.image} errors={state.errors} fileInputRef={fileInputRef} onSelectImage={selectImage} onPanelChange={(panelType) => dispatch({ type: 'set-panel', panelType })} mockScenario={state.mockScenario} onMockScenario={(scenario) => dispatch({ type: 'set-mock-scenario', scenario })} onBack={() => dispatch({ type: 'set-step', step: 'expected-values' })} onSubmit={() => void submit()} isSubmitting={state.isSubmitting} onRemove={removeImage} />}
    {state.step === 'review-extraction' && state.outcome && <ExtractionReview outcome={state.outcome} comparison={state.comparison} image={state.image} onRetry={() => void submit()} onRetryComparison={() => void retryComparison()} onBack={() => dispatch({ type: 'set-step', step: 'upload-label' })} onStartNew={startNew} isSubmitting={state.isSubmitting} />}
  </main>
}

const Field = ({ label, field, children }: { label: string; field: string; children: React.ReactNode }) => <label className="field" htmlFor={field}><span>{label}</span><small>{fieldExamples[field] ?? 'Example: select an option'}</small>{children}</label>
const TextField = ({ field, label, value, onChange, error, example, inputMode = 'text' }: { field: string; label: string; value: string; onChange: (value: string) => void; error?: string; example?: string; inputMode?: React.HTMLAttributes<HTMLInputElement>['inputMode'] }) => <label className="field" htmlFor={field}><span>{label}</span><small>{example ?? fieldExamples[field] ?? 'Example: enter the expected label value'}</small><input id={field} value={value} inputMode={inputMode} aria-invalid={Boolean(error)} aria-describedby={error ? errorId(field) : undefined} onChange={(event) => onChange(event.target.value)} />{error && <span className="field-error" id={errorId(field)}>{error}</span>}</label>

const ExpectedValues = ({ values, errors, updateValue, loadExample, onContinue }: { values: FormValues; errors: Record<string, string>; updateValue: (field: keyof FormValues, value: string | boolean) => void; loadExample: () => void; onContinue: () => void }) => <section className="workflow-card" aria-labelledby="expected-values-title"><div className="section-heading"><div><p className="step-caption">Step 1 of 3</p><h2 id="expected-values-title">Expected application values</h2></div><button type="button" className="secondary-button" onClick={loadExample}>Load synthetic example</button></div><p>Enter the values expected on the label. Government-warning wording is checked later against an approved ruleset, so it is not entered here.</p><div className="form-grid"><Field label="Beverage type" field="beverageType"><select id="beverageType" value={values.beverageType} onChange={(event) => updateValue('beverageType', event.target.value)}><option value="beer">Beer</option><option value="wine">Wine</option><option value="distilled_spirits">Distilled spirits</option></select></Field><TextField field="brandName" label="Brand name" value={values.brandName} onChange={(value) => updateValue('brandName', value)} error={errors.brandName} example="Example: Old Tom Distillery" /><TextField field="classTypeDesignation" label="Class/type designation" value={values.classTypeDesignation} onChange={(value) => updateValue('classTypeDesignation', value)} error={errors.classTypeDesignation} example="Example: Kentucky Straight Bourbon Whiskey" /><TextField field="netContentsValue" label="Net contents" inputMode="decimal" value={values.netContentsValue} onChange={(value) => updateValue('netContentsValue', value)} error={errors.netContentsValue} /><Field label="Net contents unit" field="netContentsUnit"><select id="netContentsUnit" value={values.netContentsUnit} onChange={(event) => updateValue('netContentsUnit', event.target.value)}><option value="mL">mL</option><option value="L">L</option><option value="fl_oz">Fluid ounces</option><option value="pt">Pints</option><option value="qt">Quarts</option><option value="gal">Gallons</option></select></Field>{values.beverageType === 'distilled_spirits' && <TextField field="abvPercent" label="Alcohol by volume (ABV %)" inputMode="decimal" value={values.abvPercent} onChange={(value) => updateValue('abvPercent', value)} error={errors.abvPercent} />}<TextField field="proof" label="Proof (optional)" inputMode="decimal" value={values.proof} onChange={(value) => updateValue('proof', value)} error={errors.proof} /></div><fieldset><legend>Bottler/producer name and address</legend><div className="form-grid"><TextField field="responsiblePartyName" label="Business name" value={values.responsiblePartyName} onChange={(value) => updateValue('responsiblePartyName', value)} error={errors.responsiblePartyName} /><TextField field="city" label="City" value={values.city} onChange={(value) => updateValue('city', value)} error={errors.city} /><TextField field="region" label="State, province, or region (optional)" value={values.region} onChange={(value) => updateValue('region', value)} /><TextField field="countryCode" label="Business country code" value={values.countryCode} onChange={(value) => updateValue('countryCode', value)} error={errors.countryCode} example="Example: US" /></div></fieldset><fieldset><legend>Product origin</legend><label className="checkbox-label"><input id="imported" type="checkbox" checked={values.imported} onChange={(event) => updateValue('imported', event.target.checked)} /> This is an imported product</label>{values.imported && <div className="form-grid conditional-fields"><TextField field="originCountryCode" label="Origin country code" value={values.originCountryCode} onChange={(value) => updateValue('originCountryCode', value)} error={errors.originCountryCode} example="Example: FR" /><TextField field="originDisplayName" label="Country of origin" value={values.originDisplayName} onChange={(value) => updateValue('originDisplayName', value)} error={errors.originDisplayName} /></div>}</fieldset><div className="actions"><button type="button" onClick={onContinue}>Continue to upload label</button></div></section>

const UploadLabel = ({ image, errors, fileInputRef, onSelectImage, onPanelChange, mockScenario, onMockScenario, onBack, onSubmit, isSubmitting, onRemove }: { image: PendingLabelImage | null; errors: Record<string, string>; fileInputRef: React.RefObject<HTMLInputElement | null>; onSelectImage: (file: File | undefined) => void; onPanelChange: (panel: LabelPanelType) => void; mockScenario: MockScenario; onMockScenario: (scenario: MockScenario) => void; onBack: () => void; onSubmit: () => void; isSubmitting: boolean; onRemove: () => void }) => <section className="workflow-card" aria-labelledby="upload-label-title"><p className="step-caption">Step 2 of 3</p><h2 id="upload-label-title">Upload label image</h2><p>Choose one JPEG or PNG label image up to 20 MB. The image is processed in memory and is not saved by this prototype.</p><input ref={fileInputRef} id="image" className="visually-hidden" type="file" accept="image/jpeg,image/png" aria-invalid={Boolean(errors.image)} aria-describedby={errors.image ? errorId('image') : undefined} onChange={(event) => onSelectImage(event.target.files?.[0])} /><label className="drop-zone" htmlFor="image" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); onSelectImage(event.dataTransfer.files[0]) }}><strong>Choose a label image</strong><span>or drag and drop a JPEG or PNG here</span></label>{errors.image && <p className="field-error" id={errorId('image')}>{errors.image}</p>}{image && <div className="image-details"><img src={image.previewUrl} alt={`Preview of selected label image: ${image.metadata.fileName}`} /><div><h3>{image.metadata.fileName}</h3><p>{formatBytes(image.metadata.sizeBytes)}</p><Field label="Label panel" field="panelType"><select id="panelType" value={image.metadata.panelType} onChange={(event) => onPanelChange(event.target.value as LabelPanelType)}><option value="unknown">Unknown</option><option value="brand">Brand panel</option><option value="back">Back panel</option><option value="side">Side panel</option><option value="neck">Neck panel</option><option value="other">Other panel</option></select></Field><button type="button" className="secondary-button" onClick={onRemove}>Remove image</button></div></div>}{mockControlsEnabled && <Field label="Mock OCR scenario (development only)" field="mockScenario"><select id="mockScenario" value={mockScenario} onChange={(event) => onMockScenario(event.target.value as MockScenario)}>{mockScenarios.map((scenario) => <option key={scenario.value} value={scenario.value}>{scenario.label}</option>)}</select></Field>}<div className="actions"><button type="button" className="secondary-button" onClick={onBack}>Back</button><button type="button" disabled={isSubmitting || !image} onClick={onSubmit}>{isSubmitting ? 'Analyzing label…' : 'Verify label'}</button></div></section>

const statusLabel: Record<VerificationResult['overallStatus'], string> = {
  no_discrepancies_found: 'No discrepancies found',
  review_needed: 'Review needed',
  analysis_incomplete: 'Analysis incomplete'
}

const ExtractionReview = ({ outcome, comparison, image, onRetry, onRetryComparison, onBack, onStartNew, isSubmitting }: { outcome: ExtractionApiOutcome; comparison: ComparisonApiOutcome | null; image: PendingLabelImage | null; onRetry: () => void; onRetryComparison: () => void; onBack: () => void; onStartNew: () => void; isSubmitting: boolean }) => {
  if (outcome.kind === 'network-error') return <section className="workflow-card" aria-live="polite"><p className="step-caption">Step 3 of 3</p><h2>Analysis could not start</h2><p>{outcome.message}</p><div className="actions"><button type="button" className="secondary-button" onClick={onBack}>Back to upload</button><button type="button" disabled={isSubmitting} onClick={onRetry}>Try again</button></div></section>
  if (outcome.kind === 'validation-error') return null
  if (comparison?.kind === 'completed') return <VerificationReview result={comparison.result} image={image} onBack={onBack} onStartNew={onStartNew} />
  const result = outcome.result
  const candidates = result.fieldCandidates ?? []
  const issues = result.issues ?? []
  return <section className="workflow-card extraction-review" aria-live="polite"><p className="step-caption">Step 3 of 3</p><h2>{resultHeading(result)}</h2><p className="result-disclaimer">OCR observations could not yet be compared with the approved label requirements.</p>{comparison && <p className="provider-notice">{comparison.message}</p>}{outcome.kind === 'provider-failure' && <p className="provider-notice">The analysis service was unavailable or timed out. Any observations below may be incomplete.</p>}{image && <div className="review-image"><img src={image.previewUrl} alt={`Uploaded label: ${image.metadata.fileName}`} /><p>Image: {image.metadata.fileName}</p></div>}<p className="record-reference">Submission: {result.submissionId}</p><h3>Observed label fields</h3>{candidates.length ? <dl className="candidate-list">{candidates.map((candidate) => <div key={`${candidate.field}-${candidate.rawText}`}><dt>{fieldLabels[candidate.field]}</dt><dd className={candidate.field === 'government_warning_text' ? 'verbatim-text' : undefined}>{candidate.rawText}</dd></div>)}</dl> : <p>No reliable label fields were observed.</p>}<h3>Review notes</h3>{issues.length ? <ul className="issue-list">{issues.map((issue, index) => <li key={`${issue.code}-${index}`}><strong>{issue.field ? fieldLabels[issue.field] : 'Image review'}:</strong> {issue.message}</li>)}</ul> : <p>No extraction issues were reported.</p>}<div className="actions"><button type="button" className="secondary-button" onClick={onBack}>Back to upload</button>{comparison && <button type="button" disabled={isSubmitting} onClick={onRetryComparison}>{isSubmitting ? 'Retrying…' : 'Retry comparison'}</button>}{(outcome.kind === 'provider-failure' || result.status !== 'succeeded') && <button type="button" disabled={isSubmitting} onClick={onRetry}>{isSubmitting ? 'Retrying…' : 'Try again'}</button>}<button type="button" className="secondary-button" onClick={onStartNew}>Start new review</button></div></section>
}

const VerificationReview = ({ result, image, onBack, onStartNew }: { result: VerificationResult; image: PendingLabelImage | null; onBack: () => void; onStartNew: () => void }) => <section className="workflow-card extraction-review" aria-live="polite"><p className="step-caption">Step 3 of 3</p><h2>{statusLabel[result.overallStatus]}</h2><p className="result-disclaimer">These results assist human review and are not a final compliance determination.</p>{image && <div className="review-image"><img src={image.previewUrl} alt={`Uploaded label: ${image.metadata.fileName}`} /><p>Image: {image.metadata.fileName}</p></div>}<p className="record-reference">Record: {result.recordId}<br />Submission: {result.submissionId}<br />Ruleset: {result.ruleset.rulesetId} {result.ruleset.version}</p><h3>Label requirement findings</h3><div className="finding-list">{result.findings.map((finding, index) => <article className={`finding finding--${finding.severity}`} key={`${finding.field}-${finding.ruleId}-${index}`}><h4><span aria-hidden="true">{finding.outcome === 'match' || finding.outcome === 'not_applicable' ? '✓' : finding.outcome === 'mismatch' || finding.outcome === 'not_found' ? '!' : '?'}</span> {fieldLabels[finding.field]}: {finding.outcome.replaceAll('_', ' ')}</h4><p>{finding.explanation}</p>{finding.expected && <p><strong>Expected:</strong> {finding.expected.displayValue}</p>}{finding.detected?.length ? <div><strong>Detected:</strong><ul>{finding.detected.map((value, valueIndex) => <li className={finding.field === 'government_warning_text' ? 'verbatim-text' : undefined} key={`${value.displayValue}-${valueIndex}`}>{value.displayValue}</li>)}</ul></div> : null}{finding.evidence?.length ? <p><strong>Evidence:</strong> {finding.evidence.map((evidence) => evidence.excerpt).filter(Boolean).join(' | ')}</p> : null}</article>)}</div><div className="actions"><button type="button" className="secondary-button" onClick={onBack}>Back to upload</button><button type="button" className="secondary-button" onClick={onStartNew}>Start new review</button></div></section>

type PrimaryView = 'home' | 'reviewer-hub' | 'application-input'

const Home = ({ onOpenHub, onOpenInput }: { onOpenHub: () => void; onOpenInput: () => void }) => <section className="home-options" aria-labelledby="home-title"><p className="eyebrow">Reviewer workspace</p><h2 id="home-title">Choose a workspace</h2><p>Reviewer Hub is the primary workflow for applications already processed by OCR and comparison.</p><div className="workspace-options"><button type="button" className="workspace-option workspace-option--primary" onClick={onOpenHub}><span>Primary workflow</span><strong>Open Reviewer Hub</strong><small>Review the queue, inspect evidence, then approve or reject each application.</small></button><button type="button" className="workspace-option" onClick={onOpenInput}><span>Side feature</span><strong>Application Input</strong><small>Manually enter a synthetic or exceptional application and upload one label image.</small></button></div></section>

export const App = () => {
  const [view, setView] = useState<PrimaryView>('home')
  return <main className="app-shell"><header className="app-header"><p className="eyebrow">Decision-support prototype</p><h1>Alcohol Label Verification</h1><p className="lede">Human reviewers make the final application decision. OCR and comparison results provide evidence for that review.</p><nav className="app-nav" aria-label="Primary navigation"><button type="button" className="secondary-button" onClick={() => setView('home')}>Home</button><button type="button" className="secondary-button" onClick={() => setView('reviewer-hub')}>Reviewer Hub</button><button type="button" className="secondary-button" onClick={() => setView('application-input')}>Application Input</button></nav></header>{view === 'home' && <Home onOpenHub={() => setView('reviewer-hub')} onOpenInput={() => setView('application-input')} />}{view === 'reviewer-hub' && <ReviewerHub onHome={() => setView('home')} />}{view === 'application-input' && <ApplicationInput />}</main>
}
