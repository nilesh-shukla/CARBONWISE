export type User = { id: string; email: string; created_at: string }
export type CalculationInput = {
  electricity_kwh_per_month?: number
  lpg_kg_per_month?: number
  petrol_litres_per_month?: number
  diesel_litres_per_month?: number
  region?: string
}
export type Category = { status: 'calculated' | 'not_calculated' | 'not_provided'; activity_type: string; fuel_energy_source: string; activity_amount: number | null; activity_unit: string; emissions_kg_co2: number | null; reason: string | null }
export type CalculationResult = {
  calculation_status: 'complete_for_provided_inputs' | 'partial'; total_is_partial: boolean; total_emissions_kg_co2: number; direct_emissions_kg_co2: number; indirect_emissions_kg_co2: number; categories: Record<string, Category>; not_provided_categories: string[]; excluded_categories: Record<string, string>; footprint_scope_note: string; unit: string
}
export type Calculation = { id: string; input: CalculationInput; result: CalculationResult; total_emissions_kg_co2: number; created_at: string }
type ApiError = { error?: { message?: string } }
const base = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080').replace(/\/$/, '')
let accessToken: string | null = null
let refreshPromise: Promise<boolean> | null = null

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  const response = await fetch(`${base}${path}`, { ...init, headers, credentials: 'include' })
  if (response.status === 401 && retry && !path.includes('/auth/refresh')) {
    const refreshed = await refresh()
    if (refreshed) return request<T>(path, init, false)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as ApiError | null
    throw new Error(body?.error?.message || `Request failed (${response.status})`)
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>
}
export async function refresh(): Promise<boolean> {
  if (!refreshPromise) refreshPromise = request<{ access_token: string }>('/api/auth/refresh', { method: 'POST' }, false).then((data) => { accessToken = data.access_token; return true }).catch(() => { accessToken = null; return false }).finally(() => { refreshPromise = null })
  return refreshPromise
}
export const api = {
  register: (email: string, password: string) => request<{ access_token: string; user: User }>('/api/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) }).then((d) => { accessToken = d.access_token; return d.user }),
  login: (email: string, password: string) => request<{ access_token: string; user: User }>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }).then((d) => { accessToken = d.access_token; return d.user }),
  me: () => request<{ user: User }>('/api/auth/me').then((d) => d.user),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }).finally(() => { accessToken = null }),
  calculate: (input: CalculationInput) => request<Calculation>('/api/calculations', { method: 'POST', body: JSON.stringify(input) }),
  history: (offset = 0, limit = 20) => request<{ items: Calculation[]; limit: number; offset: number }>(`/api/calculations?limit=${limit}&offset=${offset}`)
}
