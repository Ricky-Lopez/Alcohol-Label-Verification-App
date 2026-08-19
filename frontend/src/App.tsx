import { useCallback, useEffect, useState } from 'react'

type HealthResponse = {
  status: 'ok'
  service: string
}

type ServiceState =
  | { kind: 'loading' }
  | { kind: 'ready'; service: string }
  | { kind: 'error'; message: string }

const loadHealth = async (): Promise<HealthResponse> => {
  const response = await fetch('/health', {
    headers: { Accept: 'application/json' }
  })

  if (!response.ok) {
    throw new Error(`Health request failed with status ${response.status}`)
  }

  return (await response.json()) as HealthResponse
}

export const App = () => {
  const [serviceState, setServiceState] = useState<ServiceState>({ kind: 'loading' })

  const checkService = useCallback(async () => {
    setServiceState({ kind: 'loading' })

    try {
      const health = await loadHealth()
      setServiceState({ kind: 'ready', service: health.service })
    } catch {
      setServiceState({
        kind: 'error',
        message: 'The verification service is unavailable. Start the API and try again.'
      })
    }
  }, [])

  useEffect(() => {
    void checkService()
  }, [checkService])

  return (
    <main className="page-shell">
      <section className="status-card" aria-labelledby="page-title">
        <p className="eyebrow">Prototype foundation</p>
        <h1 id="page-title">Alcohol Label Verification</h1>
        <p className="summary">
          The application scaffold is ready for the first label-verification slice.
        </p>

        <div className={`service-status service-status--${serviceState.kind}`} role="status">
          {serviceState.kind === 'loading' && <p>Checking verification service…</p>}
          {serviceState.kind === 'ready' && (
            <p>
              <strong>Service ready</strong>
              <span>{serviceState.service}</span>
            </p>
          )}
          {serviceState.kind === 'error' && (
            <div>
              <p>{serviceState.message}</p>
              <button type="button" onClick={() => void checkService()}>
                Try again
              </button>
            </div>
          )}
        </div>
      </section>
    </main>
  )
}
