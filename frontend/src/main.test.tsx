import React, { useState } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, refresh, type Calculation, type CalculationResult, type User } from './api'
import { App, AuthDialog, Dashboard, History, ResultCard, Workspace } from './main'

vi.mock('./api', () => ({
  api: {
    register: vi.fn(),
    login: vi.fn(),
    me: vi.fn(),
    logout: vi.fn(),
    calculate: vi.fn(),
    history: vi.fn(),
  },
  refresh: vi.fn(),
}))

const user: User = { id: 'user-1', email: 'person@example.test', created_at: '2026-01-01T00:00:00Z' }
const emptyPage = { items: [] as Calculation[], limit: 20, offset: 0 }

function result(overrides: Partial<CalculationResult> = {}): CalculationResult {
  return {
    calculation_status: 'complete_for_provided_inputs',
    total_is_partial: false,
    total_emissions_kg_co2: 0,
    direct_emissions_kg_co2: 0,
    indirect_emissions_kg_co2: 0,
    categories: {
      electricity: {
        status: 'calculated', activity_type: 'electricity', fuel_energy_source: 'grid',
        activity_amount: 0, activity_unit: 'kWh/month', emissions_kg_co2: 0, reason: null,
      },
    },
    not_provided_categories: [],
    excluded_categories: {},
    footprint_scope_note: 'Covers supplied activities only.',
    unit: 'kgCO2/month',
    ...overrides,
  }
}

function calculation(id: string, total = 0): Calculation {
  return {
    id,
    input: { electricity_kwh_per_month: 0 },
    result: result({ total_emissions_kg_co2: total }),
    total_emissions_kg_co2: total,
    created_at: '2026-01-01T00:00:00Z',
  }
}

function setMobileViewport(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockReturnValue({
      matches,
      media: '(max-width: 800px)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  })
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(refresh).mockResolvedValue(false)
  vi.mocked(api.me).mockResolvedValue(user)
  vi.mocked(api.history).mockResolvedValue(emptyPage)
  vi.mocked(api.logout).mockResolvedValue(undefined)
})

afterEach(() => {
  Object.defineProperty(window, 'matchMedia', { configurable: true, value: undefined })
})

describe('session and navigation', () => {
  it('restores a valid session into the dashboard', async () => {
    vi.mocked(refresh).mockResolvedValue(true)

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Good to see you' })).toBeTruthy()
    expect(screen.getByText(user.email)).toBeTruthy()
  })

  it('keeps the workspace open and reports an unconfirmed logout failure', async () => {
    vi.mocked(refresh).mockResolvedValue(true)
    vi.mocked(api.logout).mockRejectedValue(new Error('network unavailable'))

    render(<App />)
    await screen.findByRole('heading', { name: 'Good to see you' })
    fireEvent.click(screen.getByRole('button', { name: /sign out/i }))

    expect((await screen.findByRole('alert')).textContent).toContain('server did not confirm sign-out')
    expect(screen.getByText(user.email)).toBeTruthy()
  })

  it('marks a closed mobile sidebar hidden and inert, with named menu controls', () => {
    setMobileViewport(true)

    const props = { user, view: 'dashboard' as const, setView: vi.fn(), onLogout: vi.fn(), logoutError: '', setMobileOpen: vi.fn() }
    const { rerender } = render(<Workspace {...props} mobileOpen={false} />)

    const sidebar = document.getElementById('workspace-sidebar')
    expect(sidebar?.getAttribute('aria-hidden')).toBe('true')
    expect(sidebar?.hasAttribute('inert')).toBe(true)
    expect(screen.queryByRole('button', { name: 'Overview' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Open navigation menu' }).getAttribute('aria-expanded')).toBe('false')

    rerender(<Workspace {...props} mobileOpen />)
    expect(sidebar?.hasAttribute('inert')).toBe(false)
    expect(screen.getByRole('button', { name: 'Overview' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Close navigation menu' })).toBeTruthy()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Overview' }))

    rerender(<Workspace {...props} mobileOpen={false} />)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Open navigation menu' }))
  })
})

describe('authentication dialog accessibility', () => {
  function DialogHarness() {
    const [open, setOpen] = useState(false)
    return <><button onClick={() => setOpen(true)}>Open dialog</button>{open && <AuthDialog mode="login" onClose={() => setOpen(false)} onSuccess={vi.fn()} />}</>
  }

  it('announces itself, focuses the first field, traps Tab, and closes on Escape restoring focus', async () => {
    render(<DialogHarness />)
    const trigger = screen.getByRole('button', { name: 'Open dialog' })
    trigger.focus()
    fireEvent.click(trigger)

    const dialog = await screen.findByRole('dialog', { name: 'Welcome back' })
    const email = screen.getByRole('textbox', { name: 'Email address' })
    expect(document.activeElement).toBe(email)
    expect(screen.getByRole('button', { name: 'Close sign in dialog' })).toBeTruthy()

    const submit = screen.getByRole('button', { name: 'Sign in' })
    submit.focus()
    fireEvent.keyDown(dialog, { key: 'Tab', code: 'Tab', bubbles: true })
    const closeButton = screen.getByRole('button', { name: 'Close sign in dialog' })
    expect(document.activeElement).toBe(closeButton)
    fireEvent.keyDown(dialog, { key: 'Tab', code: 'Tab', shiftKey: true, bubbles: true })
    expect(document.activeElement).toBe(submit)
    fireEvent.keyDown(dialog, { key: 'Escape', code: 'Escape', bubbles: true })

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(document.activeElement).toBe(trigger)
    expect(dialog.getAttribute('aria-modal')).toBe('true')
  })
})

describe('dashboard and calculation history states', () => {
  it('shows dashboard loading then empty state', async () => {
    let resolveHistory!: (value: typeof emptyPage) => void
    vi.mocked(api.history).mockReturnValue(new Promise((resolve) => { resolveHistory = resolve }))

    render(<Dashboard setView={vi.fn()} />)
    expect(screen.getByRole('status').textContent).toContain('Loading your latest calculation')

    await act(async () => resolveHistory(emptyPage))
    expect(await screen.findByText('Your first baseline starts here')).toBeTruthy()
  })

  it('shows dashboard errors and allows retry', async () => {
    vi.mocked(api.history).mockRejectedValueOnce(new Error('dashboard unavailable')).mockResolvedValueOnce(emptyPage)

    render(<Dashboard setView={vi.fn()} />)
    expect((await screen.findByRole('alert')).textContent).toContain('dashboard unavailable')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('Your first baseline starts here')).toBeTruthy()
  })

  it('shows a history error and retries successfully', async () => {
    vi.mocked(api.history).mockRejectedValueOnce(new Error('service unavailable')).mockResolvedValueOnce(emptyPage)

    render(<History />)
    expect((await screen.findByRole('alert')).textContent).toContain('service unavailable')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('No calculations yet')).toBeTruthy()
    expect(api.history).toHaveBeenCalledTimes(2)
  })

  it('paginates with the backend limit/offset contract', async () => {
    const firstPage = { items: Array.from({ length: 20 }, (_, index) => calculation(`record-${index}`)), limit: 20, offset: 0 }
    const secondPage = { items: [calculation('record-20', 1)], limit: 20, offset: 20 }
    vi.mocked(api.history).mockResolvedValueOnce(firstPage).mockResolvedValueOnce(secondPage)

    render(<History />)
    expect(await screen.findByText('Records 1–20')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    expect(await screen.findByText('Records 21–21')).toBeTruthy()
    expect(api.history).toHaveBeenLastCalledWith(20, 20)
  })
})

describe('calculation result rendering', () => {
  it('shows excluded categories and reasons', () => {
    render(<ResultCard result={result({ total_is_partial: true, calculation_status: 'partial', excluded_categories: { petrol: 'Fuel factor is unresolved.' } })} />)

    expect(screen.getByText('Excluded categories')).toBeTruthy()
    expect(screen.getByText('Fuel factor is unresolved.')).toBeTruthy()
    expect(screen.getByText('Partial — review exclusions')).toBeTruthy()
  })

  it('renders all-zero category bars with a finite width', () => {
    const { container } = render(<ResultCard result={result()} />)

    const bar = container.querySelector('.bar i')
    expect(bar?.getAttribute('style')).toContain('width: 0%')
    expect(bar?.getAttribute('style')).not.toContain('NaN')
  })
})
