import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

const healthyService = () => new Response(JSON.stringify({ status: 'ok', service: 'alcohol-label-verification-api' }), { status: 200, headers: { 'Content-Type': 'application/json' } })

describe('App', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it('shows a visible, non-blocking service state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(healthyService()))
    render(<App />)
    expect(await screen.findByText('Verification service is available.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Expected application values' })).toBeInTheDocument()
  })

  it('links blank required values to an error summary and moves focus there', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(healthyService()))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Continue to upload label' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Brand name is required.')
    expect(document.activeElement).toBe(screen.getByRole('alert'))
    expect(screen.getByRole('link', { name: 'Brand name is required.' })).toHaveAttribute('href', '#brandName')
  })

  it('loads the synthetic example and reveals imported-product fields only when needed', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(healthyService()))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }))
    expect(screen.getByDisplayValue('OLD TOM DISTILLERY')).toBeInTheDocument()
    expect(document.getElementById('originDisplayName')).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('This is an imported product'))
    expect(document.getElementById('originDisplayName')).toBeInTheDocument()
  })

  it('rejects unsupported image files before analysis', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(healthyService()))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Load synthetic example' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue to upload label' }))
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['text'], 'label.txt', { type: 'text/plain' })] } })
    expect(document.getElementById('image-error')).toHaveTextContent('Choose a JPEG or PNG image.')
    expect(screen.getByRole('button', { name: 'Verify label' })).toBeDisabled()
  })
})
