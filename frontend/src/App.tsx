import { FormEvent, useEffect, useState } from 'react'

type User = { id: string; email: string; display_name: string; role: 'user' | 'admin' }
type AdminUser = User & { is_active: boolean; created_at: string; document_count: number }
type DocumentItem = { id: string; original_name: string; content_type: string; size_bytes: number; created_at: string; is_owner: boolean; shared_by: string | null; can_view: boolean; can_download: boolean; expires_at: string | null }
type ShareItem = { id: string; email: string; display_name: string; created_at: string; can_view: boolean; can_download: boolean; expires_at: string | null; revoked_at: string | null; status: 'active' | 'expired' | 'revoked' }
type AuditItem = { id: number; event_type: string; document_id: string | null; details: string; created_at: string }

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')
const apiUrl = (path: string) => `${API_BASE_URL}${path}`

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), { ...init, credentials: 'include' })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(body.detail ?? `Request failed (${response.status})`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function App() {
  const [user, setUser] = useState<User | null>(null)
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [events, setEvents] = useState<AuditItem[]>([])
  const [mode, setMode] = useState<'login' | 'register' | 'admin' | 'bootstrap-admin'>('login')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [shareTarget, setShareTarget] = useState<DocumentItem | null>(null)
  const [shares, setShares] = useState<ShareItem[]>([])
  const [shareEmail, setShareEmail] = useState('')
  const [shareBusy, setShareBusy] = useState(false)
  const [shareCanView, setShareCanView] = useState(true)
  const [shareCanDownload, setShareCanDownload] = useState(true)
  const [shareExpiresAt, setShareExpiresAt] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [adminOpen, setAdminOpen] = useState(false)
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([])
  const [adminBusy, setAdminBusy] = useState(false)

  async function refresh() {
    const [docs, audit] = await Promise.all([api<DocumentItem[]>('/api/documents'), api<AuditItem[]>('/api/audit')])
    setDocuments(docs); setEvents(audit)
  }
  useEffect(() => { api<User>('/api/auth/me').then(setUser).catch(() => setUser(null)) }, [])
  useEffect(() => { if (user) void refresh().catch((e: Error) => setError(e.message)) }, [user])

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    const form = new FormData(event.currentTarget)
    const payload = { email: String(form.get('email') ?? ''), password: String(form.get('password') ?? ''),
      ...(['register', 'bootstrap-admin'].includes(mode) ? { display_name: String(form.get('display_name') ?? '') } : {}),
      ...(mode === 'bootstrap-admin' ? { bootstrap_token: String(form.get('bootstrap_token') ?? '') } : {}) }
    try {
      const endpoint = mode === 'register' ? '/api/auth/register' : mode === 'bootstrap-admin' ? '/api/auth/bootstrap-admin' : '/api/auth/login'
      const next = await api<User>(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      if (mode === 'admin' && next.role !== 'admin') {
        await api<void>('/api/auth/logout', { method: 'POST' })
        throw new Error('This account does not have administrator access.')
      }
      setUser(next)
    }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setNotice('')
    const input = event.currentTarget.elements.namedItem('file') as HTMLInputElement
    if (!input.files?.[0]) return
    const data = new FormData(); data.append('file', input.files[0]); setBusy(true)
    try { await api<DocumentItem>('/api/documents', { method: 'POST', body: data }); input.value = ''; setNotice('Document uploaded.'); await refresh() }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function download(item: DocumentItem) {
    setError('')
    try {
      const response = await fetch(apiUrl(`/api/documents/${item.id}/download`), { credentials: 'include' })
      if (!response.ok) { const body = await response.json().catch(() => ({})) as { detail?: string }; throw new Error(body.detail ?? 'Download failed') }
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement('a')
      link.href = url; link.download = item.original_name; link.click(); URL.revokeObjectURL(url); await refresh()
    } catch (e) { setError((e as Error).message); void refresh().catch(() => undefined) }
  }

  async function viewDocument(item: DocumentItem) {
    setError('')
    const preview = window.open('about:blank', '_blank')
    try {
      const response = await fetch(apiUrl(`/api/documents/${item.id}/view`), { credentials: 'include' })
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { detail?: string }
        throw new Error(body.detail ?? `View failed (${response.status})`)
      }
      if (!preview) throw new Error('Allow pop-ups to view this document.')
      const url = URL.createObjectURL(await response.blob())
      preview.opener = null
      preview.location.href = url
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
      await refresh()
    } catch (e) {
      preview?.close()
      setError((e as Error).message)
      void refresh().catch(() => undefined)
    }
  }

  async function openShare(item: DocumentItem) {
    setShareTarget(item); setShareEmail(''); setShareCanView(true); setShareCanDownload(true); setShareExpiresAt(''); setError(''); setShareBusy(true)
    try { setShares(await api<ShareItem[]>(`/api/documents/${item.id}/shares`)) }
    catch (e) { setError((e as Error).message) } finally { setShareBusy(false) }
  }

  async function shareDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!shareTarget) return
    setShareBusy(true); setError('')
    try {
      await api<ShareItem>(`/api/documents/${shareTarget.id}/shares`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: shareEmail, can_view: shareCanView, can_download: shareCanDownload,
          expires_at: shareExpiresAt ? new Date(shareExpiresAt).toISOString() : null }),
      })
      setShares(await api<ShareItem[]>(`/api/documents/${shareTarget.id}/shares`))
      setShareEmail(''); setNotice(`Shared “${shareTarget.original_name}” with ${shareEmail}.`)
    } catch (e) { setError((e as Error).message) } finally { setShareBusy(false) }
  }

  async function revokeShare(share: ShareItem) {
    if (!shareTarget) return
    setShareBusy(true); setError('')
    try {
      await api<void>(`/api/documents/${shareTarget.id}/shares/${share.id}`, { method: 'DELETE' })
      setShares(current => current.map(item => item.id === share.id
        ? { ...item, revoked_at: new Date().toISOString(), status: 'revoked' } : item))
      setNotice(`Removed ${share.email}’s access.`)
    } catch (e) { setError((e as Error).message) } finally { setShareBusy(false) }
  }

  async function toggleAdminPanel() {
    if (adminOpen) { setAdminOpen(false); return }
    setAdminOpen(true); setAdminBusy(true); setError('')
    try { setAdminUsers(await api<AdminUser[]>('/api/admin/users')) }
    catch (e) { setError((e as Error).message) } finally { setAdminBusy(false) }
  }

  async function toggleUserStatus(managedUser: AdminUser) {
    setAdminBusy(true); setError('')
    try {
      const updated = await api<AdminUser>(`/api/admin/users/${managedUser.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !managedUser.is_active }),
      })
      setAdminUsers(current => current.map(item => item.id === updated.id ? updated : item))
      setNotice(`${updated.display_name}’s account is now ${updated.is_active ? 'active' : 'disabled'}.`)
    } catch (e) { setError((e as Error).message) } finally { setAdminBusy(false) }
  }

  async function logout() {
    await api<void>('/api/auth/logout', { method: 'POST' }); setUser(null); setDocuments([]); setEvents([])
  }

  if (!user) return <main className="auth-shell"><section className="brand-panel"><div className="brand"><span className="brand-mark">T</span> TrustVault</div><div><p className="eyebrow">PRIVATE BY DEFAULT</p><h1>Your documents,<br />kept in good hands.</h1><p className="muted light">A simple, secure place for the files that matter.</p></div><div className="brand-foot">Encrypted sessions · Private document storage</div></section><section className="auth-panel"><div className="auth-card"><p className="eyebrow">WELCOME TO TRUSTVAULT</p><h2>{mode === 'admin' ? 'Administrator sign in' : mode === 'bootstrap-admin' ? 'Set up first administrator' : mode === 'login' ? 'Sign in to your vault' : 'Create your account'}</h2><p className="muted">{mode === 'admin' ? 'Sign in with an administrator account.' : mode === 'bootstrap-admin' ? 'Enter the private setup code from Render. This works only before the first admin is created.' : mode === 'login' ? 'Pick up where you left off.' : 'Your own private document space.'}</p>
    <form onSubmit={submitAuth} className="form-stack">{(mode === 'register' || mode === 'bootstrap-admin') && <label>Your name<input name="display_name" autoComplete="name" placeholder="Alex Morgan" /></label>}<label>Email address<input name="email" type="email" autoComplete="email" required placeholder="you@example.com" /></label><label>Password<div className="password-input-wrap"><input name="password" type={showPassword ? 'text' : 'password'} autoComplete={mode === 'register' || mode === 'bootstrap-admin' ? 'new-password' : 'current-password'} minLength={12} required placeholder="At least 12 characters" /><button type="button" className="password-toggle" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'} title={showPassword ? 'Hide password' : 'Show password'}><svg viewBox="0 0 24 24" aria-hidden="true">{showPassword ? <><path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8"/><path d="M9.9 5.2A11 11 0 0 1 12 5c6.4 0 10 7 10 7a16 16 0 0 1-3.1 3.8M6.2 6.2C3.5 8 2 12 2 12s3.6 7 10 7a10 10 0 0 0 4-.8"/></> : <><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></>}</svg></button></div></label>{mode === 'bootstrap-admin' && <label>Private Render setup code<input name="bootstrap_token" type="password" autoComplete="off" minLength={32} required placeholder="Paste the generated setup code" /></label>}<button className="primary" disabled={busy}>{busy ? 'Please wait…' : mode === 'register' ? 'Create account' : mode === 'bootstrap-admin' ? 'Set up administrator' : mode === 'admin' ? 'Admin sign in' : 'Sign in'} <span>→</span></button></form>
    {error && <p className="alert" role="alert">{error}</p>}{mode === 'admin' ? <p className="switch">Not an administrator? <button className="link" onClick={() => { setMode('login'); setError('') }}>User sign in</button></p> : mode === 'bootstrap-admin' ? <p className="switch">Already have an account? <button className="link" onClick={() => { setMode('login'); setError('') }}>User sign in</button></p> : <p className="switch">{mode === 'login' ? 'New to TrustVault?' : 'Already have an account?'} <button className="link" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>{mode === 'login' ? 'Create an account' : 'Sign in'}</button></p>}{mode === 'login' && <><button className="admin-entry" onClick={() => { setMode('admin'); setError('') }}>Admin sign in <span>→</span></button><button className="admin-entry" onClick={() => { setMode('bootstrap-admin'); setError('') }}>Set up first administrator <span>→</span></button></>}</div></section></main>

  return <div className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark">T</span> TrustVault</div><div className="nav-label">WORKSPACE</div><a className="nav-item active" href="#documents"><span>▤</span> My documents</a><div className="sidebar-bottom"><div className="avatar">{user.display_name.slice(0, 1).toUpperCase()}</div><div className="user-meta"><strong>{user.display_name}</strong><span>{user.email}</span></div><button className="signout-button" onClick={() => void logout()} aria-label="Sign out"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 17l5-5-5-5M15 12H3"/><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6"/></svg><span>Sign out</span></button></div></aside>
    <main className="main-content"><header className="topbar"><div><p className="eyebrow">YOUR PRIVATE WORKSPACE</p><h1>Documents</h1></div><div className="topbar-actions">{user.role === 'admin' && <button className={`admin-button ${adminOpen ? 'selected' : ''}`} onClick={() => void toggleAdminPanel()}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 4 6v5c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V6l-8-3Z"/><path d="m9 12 2 2 4-4"/></svg>{adminOpen ? 'Close admin' : 'Admin'}</button>}<div className="secure-badge"><span></span> Private &amp; secure</div></div></header>
      <section className="welcome"><div><p className="eyebrow light">YOUR VAULT</p><h2>Everything important,<br />in one place.</h2><p>Upload and manage your private documents.</p></div><div className="welcome-art" aria-hidden="true"><div className="orb"></div><div className="doc-shape">▤</div></div></section>
      {error && <p className="alert page-alert" role="alert">{error}</p>}{notice && <p className="success page-alert">{notice}</p>}
      {adminOpen && user.role === 'admin' && <section className="admin-panel"><div className="section-heading"><div><h2>Manage login users</h2><p>Disable or restore regular user accounts. Admin accounts are protected.</p></div><span className="count-pill">{adminUsers.length.toString().padStart(2, '0')}</span></div>{adminBusy && adminUsers.length === 0 ? <p className="muted">Loading users…</p> : adminUsers.length ? <div className="admin-user-list">{adminUsers.map(account => <article className="admin-user-row" key={account.id}><div className="avatar">{account.display_name.slice(0, 1).toUpperCase()}</div><div className="admin-user-info"><strong>{account.display_name}</strong><span>{account.email}</span></div><span className={`account-status ${account.is_active ? 'active' : 'disabled'}`}>{account.role === 'admin' ? 'Admin' : account.is_active ? 'Active' : 'Disabled'}</span>{account.role === 'user' && <button className="user-status-button" disabled={adminBusy} onClick={() => void toggleUserStatus(account)}>{account.is_active ? 'Disable' : 'Enable'}</button>}</article>)}</div> : <div className="empty-state"><h3>No accounts found</h3></div>}</section>}
      <section className="upload-card"><div className="upload-icon">↑</div><div className="upload-copy"><h3>Add a document</h3><p>PDF, text, CSV, Word, or image. Maximum 10 MB.</p></div><form onSubmit={upload} className="upload-form"><input type="file" name="file" accept=".pdf,.txt,.md,.csv,.png,.jpg,.jpeg,.docx" required /><button className="primary compact" disabled={busy}>Upload file <span>↑</span></button></form></section>
      <section id="documents" className="documents-section"><div className="section-heading"><div><h2>Your files</h2><p>{documents.length} {documents.length === 1 ? 'document' : 'documents'} in your vault</p></div><span className="count-pill">{documents.length.toString().padStart(2, '0')}</span></div>
        {documents.length ? <div className="file-list">{documents.map(item => <article className="file-row" key={item.id}><div className="file-icon">{item.original_name.split('.').pop()?.toUpperCase().slice(0, 3)}</div><div className="file-info"><strong>{item.original_name}</strong><span>{formatBytes(item.size_bytes)} · {item.is_owner ? 'Added' : `Shared by ${item.shared_by}`} {new Date(item.created_at).toLocaleDateString()}{!item.is_owner && item.expires_at && ` · Expires ${new Date(item.expires_at).toLocaleString()}`}</span></div><div className="file-actions">{item.can_view && <button className="action-icon" onClick={() => void viewDocument(item)} aria-label={`View ${item.original_name}`} title="View"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.6"/></svg></button>}{item.is_owner && <button className="action-icon" onClick={() => void openShare(item)} aria-label={`Share ${item.original_name}`} title="Share"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.7 10.6 6.6-4.2M8.7 13.4l6.6 4.2"/></svg></button>}{item.can_download && <button className="action-icon" onClick={() => void download(item)} aria-label={`Download ${item.original_name}`} title="Download"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M4 17v3h16v-3"/></svg></button>}</div></article>)}</div> : <div className="empty-state"><div className="empty-icon">▤</div><h3>Your vault is ready</h3><p>Upload your first document and it will appear here.</p></div>}
      </section>
      <section className="activity"><div className="section-heading"><div><h2>Recent activity</h2><p>Latest actions in your vault</p></div></div>{events.length ? <div className="activity-list">{events.slice(0, 5).map(event => <div className="activity-row" key={event.id}><span className="activity-dot"></span><span>{describeActivity(event)}</span><time>{new Date(event.created_at).toLocaleString()}</time></div>)}</div> : <p className="muted">Activity will appear here.</p>}</section>
      <footer className="page-footer">TrustVault prototype <span>·</span> Your data stays in your local environment</footer>
    </main>{shareTarget && <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setShareTarget(null) }}><section className="share-dialog" role="dialog" aria-modal="true" aria-labelledby="share-title"><button className="modal-close" onClick={() => setShareTarget(null)} aria-label="Close sharing dialog">×</button><p className="eyebrow">DOCUMENT ACCESS</p><h2 id="share-title">Share a document</h2><p className="muted">{shareTarget.original_name} · choose view and download rights, with an optional expiry.</p><form className="share-form" onSubmit={shareDocument}><label htmlFor="share-email">TrustVault account email</label><div><input id="share-email" type="email" required value={shareEmail} onChange={event => setShareEmail(event.target.value)} placeholder="person@example.com" /><button className="primary" disabled={shareBusy || !shareEmail.trim() || (!shareCanView && !shareCanDownload)}>{shareBusy ? 'Please wait…' : 'Share'}</button></div><div className="share-options"><label><input type="checkbox" checked={shareCanView} onChange={event => setShareCanView(event.target.checked)} /> Can view</label><label><input type="checkbox" checked={shareCanDownload} onChange={event => setShareCanDownload(event.target.checked)} /> Can download</label></div><label className="expiry-label" htmlFor="share-expiry">Access expires (optional)</label><input className="expiry-input" id="share-expiry" type="datetime-local" value={shareExpiresAt} onChange={event => setShareExpiresAt(event.target.value)} /><small>The person must have a TrustVault account. You can revoke access below.</small></form>{error && <p className="alert" role="alert">{error}</p>}<div className="share-list"><h3>People with access</h3>{shareBusy && shares.length === 0 ? <p className="muted">Loading access…</p> : shares.length ? shares.map(share => <div className="share-person" key={share.id}><span className="avatar">{share.display_name.slice(0, 1).toUpperCase()}</span><span><strong>{share.display_name}</strong><small>{share.email}</small><small>{[share.can_view && 'View', share.can_download && 'Download'].filter(Boolean).join(' · ')}{share.expires_at ? ` · expires ${new Date(share.expires_at).toLocaleString()}` : ' · no expiry'} · {share.status}</small></span>{share.status === 'active' && <button className="revoke-button" disabled={shareBusy} onClick={() => void revokeShare(share)}>Revoke</button>}</div>) : <p className="muted">Only you can access this document so far.</p>}</div></section></div>}</div>
}

function formatBytes(bytes: number) { return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB` }

function describeActivity(event: AuditItem) {
  if (event.event_type !== 'document_access_denied') return event.event_type.replaceAll('_', ' ')
  try {
    const details = JSON.parse(event.details) as { reason?: string }
    const reasons: Record<string, string> = {
      document_not_found: 'This document is not available to your account.',
      share_revoked: 'The document share was revoked.',
      share_expired: 'The document share expired.',
      view_permission_not_granted: 'View permission was not granted.',
      download_permission_not_granted: 'Download permission was not granted.',
    }
    return `Access denied: ${reasons[details.reason ?? ''] ?? 'You do not have permission for this action.'}`
  } catch {
    return 'Access denied: You do not have permission for this action.'
  }
}

export default App
