import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowRight, BarChart3, Check, ChevronLeft, CircleUserRound, Gauge, Leaf, LogOut, Menu, Play, ShieldCheck, Sparkles, X, AlertTriangle, RefreshCw, Loader2 } from 'lucide-react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, Calculation, CalculationInput, CalculationResult, User, refresh } from './api'
import './styles.css';
import './overrides.css'

const fields = [
  ['electricity_kwh_per_month', 'Grid electricity', 'kWh / month', 'Typical monthly electricity bill or meter reading'],
  ['lpg_kg_per_month', 'LPG consumption', 'kg / month', 'Estimate from cylinder size and refill frequency'],
  ['petrol_litres_per_month', 'Petrol', 'litres / month', 'Optional — currently reported as unresolved by the backend'],
  ['diesel_litres_per_month', 'Diesel', 'litres / month', 'Optional — currently reported as unresolved by the backend']
] as const
type View = 'home' | 'dashboard' | 'calculator' | 'history' | 'settings'

export function App() {
  const [user, setUser] = useState<User | null>(null)
  const [view, setView] = useState<View>('home')
  const [booting, setBooting] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [logoutError, setLogoutError] = useState('')
  useEffect(() => {
    let active = true
    async function restoreSession() {
      try {
        if (await refresh()) {
          const restoredUser = await api.me()
          if (active) {
            setUser(restoredUser)
            setView('dashboard')
          }
        }
      } catch {
        // An expired or unavailable session leaves the user on the public landing page.
      } finally {
        if (active) setBooting(false)
      }
    }
    void restoreSession()
    return () => { active = false }
  }, [])
  async function logout() {
    setLogoutError('')
    try {
      await api.logout()
      setUser(null)
      setView('home')
    } catch {
      setLogoutError('The server did not confirm sign-out. Your workspace remains open; please retry.')
    }
  }
  if (booting) return (
    <div className="splash">
      <div className="splash-icon-wrap"><Leaf size={32} className="splash-spinner" /></div>
      <span>Loading your workspace…</span>
    </div>
  )
  return <>{user ? <Workspace user={user} view={view} setView={(v) => { setView(v); setMobileOpen(false) }} onLogout={logout} logoutError={logoutError} mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} /> : <Landing onAuth={(u) => { setUser(u); setView('dashboard') }} />}</>
}

function Landing({ onAuth }: { onAuth: (u: User) => void }) {
  const [auth, setAuth] = useState<'login' | 'register' | null>(null)
  return <main className="landing"><header className="public-nav"><a className="brand" href="#"><span className="brand-mark"><Leaf size={18} /></span>CARBON<span>WISE</span></a><nav><a href="#method">Methodology</a><a href="#features">What we measure</a><button className="button ghost" onClick={() => setAuth('login')}>Sign in</button><button className="button dark" onClick={() => setAuth('register')}>Get started <ArrowRight size={16} /></button></nav></header><section className="hero"><div className="hero-copy"><p className="eyebrow"><Sparkles size={15} /> Household climate intelligence</p><h1>Know your footprint.<br /><em>Change what matters.</em></h1><p className="hero-text">A clear, evidence-led way to understand the emissions behind everyday household consumption in India.</p><div className="hero-actions"><button className="button dark large" onClick={() => setAuth('register')}>Calculate my footprint <ArrowRight size={18} /></button><a className="learn" href="#method"><Play size={15} /> How it works</a></div><div className="trust"><ShieldCheck size={17} /><span>Transparent factors</span><span className="dot" /><span>Private by design</span></div></div><Preview /></section><section className="feature-strip" id="features"><Feature icon={<Gauge />} title="Personal, not generic" text="Your actual monthly activity, translated into a useful baseline." /><Feature icon={<BarChart3 />} title="See the drivers" text="Understand which supplied categories contribute most." /><Feature icon={<ShieldCheck />} title="Honest by default" text="Missing inputs stay missing. No invented precision." /></section><section className="method" id="method"><div><p className="eyebrow">The CARBONWISE approach</p><h2>Useful clarity, without the black box.</h2></div><p>CARBONWISE applies versioned emission factors to the activities you provide. Each result shows its scope, assumptions, and coverage so you can make informed decisions about what to measure next.</p></section>{auth && <AuthDialog mode={auth} onClose={() => setAuth(null)} onSuccess={onAuth} />}</main>
}
function Preview() { const data = [{ m: 'Jan', v: 64 }, { m: 'Feb', v: 56 }, { m: 'Mar', v: 61 }, { m: 'Apr', v: 47 }, { m: 'May', v: 51 }, { m: 'Jun', v: 43 }]; return <motion.div className="preview-card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .15 }}><div className="preview-top"><span>Sample dashboard</span><span className="sample-badge">DEMO DATA</span></div><div className="preview-total"><span>Monthly footprint</span><strong>51.8 <small>kgCO₂</small></strong><span className="positive">↓ 12.4% vs. baseline</span></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data}><defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#70a894" stopOpacity=".4" /><stop offset="100%" stopColor="#70a894" stopOpacity="0" /></linearGradient></defs><XAxis dataKey="m" tickLine={false} axisLine={false} tick={{ fill: '#94a69e', fontSize: 11 }} /><YAxis hide /><Tooltip contentStyle={{ border: 0, borderRadius: 10, fontSize: 12 }} /><Area type="monotone" dataKey="v" stroke="#70a894" fill="url(#fill)" strokeWidth={2} /></AreaChart></ResponsiveContainer></div><div className="preview-foot"><span><i className="legend electricity" /> Electricity</span><span><i className="legend lpg" /> LPG</span><span>Monthly · India</span></div></motion.div> }
function Feature({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) { return <div className="feature"><div className="feature-icon">{icon}</div><h3>{title}</h3><p>{text}</p></div> }

export function AuthDialog({ mode, onClose, onSuccess }: { mode: 'login' | 'register'; onClose: () => void; onSuccess: (u: User) => void }) {
  const [email, setEmail] = useState(''); const [password, setPassword] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const dialogRef = useRef<HTMLDivElement>(null)
  const emailRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    emailRef.current?.focus()
    return () => {
      previouslyFocused?.focus()
    }
  }, [])
  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
      return
    }
    if (event.key !== 'Tab') return
    const dialog = dialogRef.current
    if (!dialog) return
    const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('*')).filter((element) => element.tabIndex >= 0 && !element.matches(':disabled') && element.getAttribute('aria-hidden') !== 'true')
    if (!focusable.length) {
      event.preventDefault()
      dialog.focus()
      return
    }
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
      event.preventDefault()
      first.focus()
    }
  }
  async function submit(e: React.FormEvent) { e.preventDefault(); setError(''); setBusy(true); try { const u = mode === 'login' ? await api.login(email, password) : await api.register(email, password); onSuccess(u) } catch (err) { setError(err instanceof Error ? err.message : 'Unable to continue') } finally { setBusy(false) } }
  return <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}><motion.div ref={dialogRef} onKeyDown={handleKeyDown} className="modal" role="dialog" aria-modal="true" aria-labelledby="auth-dialog-title" aria-describedby="auth-dialog-description" tabIndex={-1} initial={{ opacity: 0, scale: .96 }} animate={{ opacity: 1, scale: 1 }}><button className="close" aria-label={mode === 'login' ? 'Close sign in dialog' : 'Close account creation dialog'} onClick={onClose}><X size={18} /></button><span className="brand-mark"><Leaf size={18} /></span><h2 id="auth-dialog-title">{mode === 'login' ? 'Welcome back' : 'Start with your baseline'}</h2><p id="auth-dialog-description" className="muted">{mode === 'login' ? 'Sign in to continue to your workspace.' : 'Create a private workspace for your household data.'}</p><form onSubmit={submit}><label>Email address<input ref={emailRef} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label><label>Password<input type="password" required minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} /><small>At least 12 characters.</small></label>{error && <div className="error" role="alert">{error}</div>}<button className="button dark full" disabled={busy}>{busy ? <><Loader2 size={16} className="button-spinner" /> Working…</> : mode === 'login' ? 'Sign in' : 'Create account'} <ArrowRight size={16} /></button></form></motion.div></div>
}

export function Workspace({ user, view, setView, onLogout, logoutError, mobileOpen, setMobileOpen }: { user: User; view: View; setView: (v: View) => void; onLogout: () => Promise<void>; logoutError: string; mobileOpen: boolean; setMobileOpen: (v: boolean) => void }) {
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia?.('(max-width: 800px)').matches === true)
  const sidebarRef = useRef<HTMLElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const wasMobileOpen = useRef(false)
  const sidebarHidden = isMobile && !mobileOpen
  useEffect(() => {
    if (!window.matchMedia) return
    const media = window.matchMedia('(max-width: 800px)')
    function updateLayout() {
      setIsMobile(media.matches)
      if (!media.matches) setMobileOpen(false)
    }
    media.addEventListener('change', updateLayout)
    return () => media.removeEventListener('change', updateLayout)
  }, [setMobileOpen])
  useEffect(() => {
    if (isMobile && mobileOpen) sidebarRef.current?.querySelector<HTMLButtonElement>('.nav-item')?.focus()
    else if (isMobile && wasMobileOpen.current) menuButtonRef.current?.focus()
    wasMobileOpen.current = isMobile && mobileOpen
  }, [isMobile, mobileOpen])
  return <div className="app-shell"><aside ref={sidebarRef} id="workspace-sidebar" aria-hidden={sidebarHidden} {...(sidebarHidden ? { inert: '' } : {})} className={mobileOpen ? 'sidebar open' : 'sidebar'}><div className="side-brand"><a className="brand" href="#"><span className="brand-mark"><Leaf size={18} /></span>CARBON<span>WISE</span></a><button className="close mobile-close" aria-label="Close navigation menu" onClick={() => setMobileOpen(false)}><X size={18} /></button></div><p className="nav-label">Workspace</p><Nav icon={<Gauge />} label="Overview" active={view === 'dashboard'} onClick={() => setView('dashboard')} /><Nav icon={<Sparkles />} label="New calculation" active={view === 'calculator'} onClick={() => setView('calculator')} /><Nav icon={<BarChart3 />} label="History" active={view === 'history'} onClick={() => setView('history')} /><p className="nav-label account-label">Account</p><Nav icon={<CircleUserRound />} label="Settings" active={view === 'settings'} onClick={() => setView('settings')} /><button className="logout" onClick={() => { void onLogout() }}><LogOut size={17} /> Sign out</button><div className="side-note"><Leaf size={16} /><span>Small changes become meaningful when you can see them.</span></div></aside><main className="workspace"><header className="app-header"><button ref={menuButtonRef} className="menu-button" aria-label="Open navigation menu" aria-controls="workspace-sidebar" aria-expanded={mobileOpen} onClick={() => setMobileOpen(true)}><Menu /></button><div><p className="eyebrow">Personal workspace</p><h1>{view === 'dashboard' ? 'Good to see you' : view === 'calculator' ? 'New calculation' : view === 'history' ? 'Calculation history' : 'Account settings'}</h1></div><div className="user-chip"><span>{user.email.slice(0, 1).toUpperCase()}</span>{user.email}</div></header><div className="content">{logoutError && <div className="error" role="alert">{logoutError}</div>}<AnimatePresence mode="wait">{view === 'dashboard' && <Dashboard key="dash" setView={setView} />}{view === 'calculator' && <Calculator key="calc" />}{view === 'history' && <History key="history" />}{view === 'settings' && <Settings key="settings" user={user} onLogout={onLogout} />}</AnimatePresence></div></main></div>
}
function Nav({ icon, label, active, onClick }: { icon: React.ReactNode; label: string; active: boolean; onClick: () => void }) { return <button className={active ? 'nav-item active' : 'nav-item'} onClick={onClick}>{icon}<span>{label}</span>{active && <span className="active-dot" />}</button> }
export function Dashboard({ setView }: { setView: (v: View) => void }) {
  const [latest, setLatest] = useState<Calculation | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  async function loadLatest() {
    setLoading(true)
    setError('')
    try {
      const response = await api.history()
      setLatest(response.items[0] || null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load your latest calculation')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { void loadLatest() }, [])
  const total = latest?.result.total_emissions_kg_co2 ?? latest?.total_emissions_kg_co2
  return <motion.div className="page" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}><div className="welcome-row"><div><p className="eyebrow">Your latest snapshot</p><h2>Make your baseline visible.</h2><p className="muted">Start with the activities you know. Add more detail over time.</p></div><button className="button dark" onClick={() => setView('calculator')}>New calculation <ArrowRight size={16} /></button></div>{loading ? (
    <div className="empty-card loading-state" role="status">
      <div className="state-icon loading-spin"><Loader2 size={30} /></div>
      <p>Loading your latest calculation…</p>
      <div className="skeleton-grid">
        <div className="skeleton-card" />
        <div className="skeleton-card" />
        <div className="skeleton-card" />
      </div>
    </div>
  ) : error ? (
    <div className="empty-card error-state">
      <div className="state-icon error-icon"><AlertTriangle size={28} /></div>
      <h3>Could not load your dashboard</h3>
      <p className="error" role="alert">{error}</p>
      <button className="button outline" onClick={() => { void loadLatest() }}><RefreshCw size={15} /> Retry</button>
    </div>
  ) : <><div className="metric-grid"><div className="metric-card primary"><span>Latest monthly footprint</span><strong>{total !== undefined ? total.toFixed(1) : '—'} <small>kgCO₂</small></strong><p>{latest ? new Date(latest.created_at).toLocaleDateString() : 'No calculation yet'}</p></div><div className="metric-card"><span>Indirect emissions</span><strong>{latest ? latest.result.indirect_emissions_kg_co2.toFixed(1) : '—'} <small>kgCO₂</small></strong><p>Scope 2 · electricity</p></div><div className="metric-card"><span>Direct emissions</span><strong>{latest ? latest.result.direct_emissions_kg_co2.toFixed(1) : '—'} <small>kgCO₂</small></strong><p>Scope 1 · supplied fuels</p></div></div>{latest ? <ResultCard result={latest.result} /> : <div className="empty-card"><div className="feature-icon"><Sparkles /></div><h3>Your first baseline starts here</h3><p className="muted">A two-minute calculation gives you a clear, honest starting point.</p><button className="button outline" onClick={() => setView('calculator')}>Calculate my footprint <ArrowRight size={16} /></button></div>}</>}</motion.div>
}
function Calculator() { const [values, setValues] = useState<Record<string, string>>({}); const [region, setRegion] = useState('India'); const [result, setResult] = useState<CalculationResult | null>(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); function change(k: string, v: string) { setValues((x) => ({ ...x, [k]: v })) } async function submit(e: React.FormEvent) { e.preventDefault(); setError(''); const input: CalculationInput = { region }; for (const [key, value] of Object.entries(values)) if (value.trim() !== '') { const number = Number(value); if (!Number.isFinite(number) || number < 0) { setError('Enter non-negative numbers, or leave optional fields blank.'); return } input[key as keyof CalculationInput] = number as never } if (Object.keys(input).length === 1) { setError('Provide at least one activity to calculate.'); return } setBusy(true); try { const saved = await api.calculate(input); setResult(saved.result) } catch (err) { setError(err instanceof Error ? err.message : 'Calculation failed') } finally { setBusy(false) } } return <motion.div className="page calculator-page" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>{result ? <><div className="result-heading"><div><p className="eyebrow">{result.total_is_partial ? 'Partial calculation' : 'Calculation complete'}</p><h2>Your footprint snapshot</h2></div><button className="button outline" onClick={() => setResult(null)}><ChevronLeft size={16} /> Edit inputs</button></div><ResultCard result={result} /></> : <><div className="welcome-row"><div><p className="eyebrow">Monthly · India</p><h2>What does your household use?</h2><p className="muted">Add the activities you have data for. Blank fields stay out of the result.</p></div></div><form className="calculator-form" onSubmit={submit}><div className="form-section"><div className="section-title"><span>01</span><div><h3>Household activity</h3><p className="muted">Use your most recent typical month.</p></div></div><div className="input-grid">{fields.map(([key, label, unit, help]) => <label key={key}>{label}<div className="input-wrap"><input inputMode="decimal" type="number" min="0" step="any" placeholder="Not provided" value={values[key] || ''} onChange={(e) => change(key, e.target.value)} /><span>{unit}</span></div><small>{help}</small></label>)}</div><label className="region">Region<select value={region} onChange={(e) => setRegion(e.target.value)}><option>India</option></select><small>Used for factor resolution where supported.</small></label></div>{error && <div className="error" role="alert">{error}</div>}<div className="form-footer"><p><ShieldCheck size={16} /> Your inputs are only used for your account calculation.</p><button className="button dark" disabled={busy}>{busy ? <><Loader2 size={16} className="button-spinner" /> Calculating…</> : 'Review and calculate'} <ArrowRight size={16} /></button></div></form></>}</motion.div> }
export function ResultCard({ result }: { result: CalculationResult }) {
  const data = Object.entries(result.categories).filter(([, category]) => category.status === 'calculated' && category.emissions_kg_co2 !== null).map(([name, category]) => ({ name: name.replace(/_/g, ' '), value: category.emissions_kg_co2 as number }))
  const maxValue = Math.max(0, ...data.map((category) => category.value))
  const excluded = Object.entries(result.excluded_categories)
  return <div className="result-card"><div className="result-main"><span>Total for supplied activities</span><strong>{result.total_emissions_kg_co2.toFixed(2)} <small>kgCO₂ / month</small></strong><span className={result.total_is_partial ? 'status warning' : 'status'}>{result.total_is_partial ? 'Partial — review exclusions' : 'Complete for provided inputs'}</span></div><div className="breakdown"><h3>Category breakdown</h3>{data.length ? data.map((category) => <div className="bar-row" key={category.name}><div><span>{category.name}</span><b>{category.value.toFixed(2)} kg</b></div><div className="bar"><i style={{ width: `${maxValue > 0 ? Math.max(4, category.value / maxValue * 100) : 0}%` }} /></div></div>) : <p className="muted">No supplied categories could be calculated.</p>}</div><div className="coverage"><div><Check size={15} /><span>Calculated: {result.calculation_status === 'complete_for_provided_inputs' ? 'all supplied categories' : Object.keys(result.categories).filter((key) => result.categories[key].status === 'calculated').join(', ')}</span></div><div><CircleUserRound size={15} /><span>Not provided: {result.not_provided_categories.join(', ') || 'none'}</span></div>{excluded.length > 0 && <div className="excluded-categories"><strong>Excluded categories</strong><ul>{excluded.map(([category, reason]) => <li key={category}><b>{category}:</b> {reason}</li>)}</ul></div>}<p>{result.footprint_scope_note}</p></div></div>
}
export function History() {
  const [items, setItems] = useState<Calculation[]>([])
  const [limit, setLimit] = useState(20)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  async function loadPage(nextOffset: number) {
    setLoading(true)
    setError('')
    try {
      const response = await api.history(nextOffset, limit)
      setItems(response.items)
      setLimit(response.limit)
      setOffset(response.offset)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load history')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { void loadPage(0) }, [])
  const hasNextPage = items.length === limit
  return <motion.div className="page" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}><div className="welcome-row"><div><p className="eyebrow">Private to your account</p><h2>Your calculation history</h2><p className="muted">A record of the snapshots you have created.</p></div></div>{loading ? (
    <div className="empty-card loading-state" role="status">
      <div className="state-icon loading-spin"><Loader2 size={30} /></div>
      <p>Loading your calculation history…</p>
      <div className="skeleton-list">
        <div className="skeleton-row" />
        <div className="skeleton-row" />
        <div className="skeleton-row" />
      </div>
    </div>
  ) : error ? (
    <div className="empty-card error-state">
      <div className="state-icon error-icon"><AlertTriangle size={28} /></div>
      <h3>Could not load history</h3>
      <p className="error" role="alert">{error}</p>
      <button className="button outline" onClick={() => { void loadPage(offset) }}><RefreshCw size={15} /> Retry</button>
    </div>
  ) : items.length ? <><div className="history-list">{items.map((item) => <div className="history-row" key={item.id}><div className="history-icon"><BarChart3 size={18} /></div><div><strong>{new Date(item.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}</strong><span>{item.result.total_is_partial ? 'Partial calculation' : 'Complete for supplied inputs'}</span></div><b>{item.total_emissions_kg_co2.toFixed(2)} <small>kgCO₂</small></b><ArrowRight size={17} /></div>)}</div><div className="history-pagination"><button className="button outline" disabled={offset === 0} onClick={() => { void loadPage(Math.max(0, offset - limit)) }}>Previous</button><span>Records {offset + 1}–{offset + items.length}</span><button className="button outline" disabled={!hasNextPage} onClick={() => { void loadPage(offset + limit) }}>Next</button></div></> : <div className="empty-card"><div className="feature-icon"><BarChart3 /></div><h3>{offset === 0 ? 'No calculations yet' : 'No more calculations'}</h3><p className="muted">{offset === 0 ? 'Your completed snapshots will appear here.' : 'You have reached the end of your calculation history.'}</p>{offset > 0 && <button className="button outline" onClick={() => { void loadPage(Math.max(0, offset - limit)) }}>Previous page</button>}</div>}</motion.div>
}
function Settings({ user, onLogout }: { user: User; onLogout: () => Promise<void> }) { return <motion.div className="page narrow-page" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}><div className="welcome-row"><div><p className="eyebrow">Account</p><h2>Your settings</h2><p className="muted">Manage your session and review account details.</p></div></div><div className="settings-card"><div className="setting"><span>Email address</span><strong>{user.email}</strong></div><div className="setting"><span>Member since</span><strong>{new Date(user.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}</strong></div><button className="button outline danger" onClick={() => { void onLogout() }}><LogOut size={16} /> Sign out</button></div></motion.div> }

const rootElement = document.getElementById('root')
if (rootElement) createRoot(rootElement).render(<React.StrictMode><App /></React.StrictMode>)
