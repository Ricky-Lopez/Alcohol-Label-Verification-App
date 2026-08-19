import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the service as ready when the health check succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ status: 'ok', service: 'alcohol-label-verification-api' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      )
    )

    render(<App />)

    expect(await screen.findByText('Service ready')).toBeInTheDocument()
    expect(screen.getByText('alcohol-label-verification-api')).toBeInTheDocument()
  })

  it('offers a retry when the health check fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unavailable')))

    render(<App />)

    expect(await screen.findByText(/verification service is unavailable/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
