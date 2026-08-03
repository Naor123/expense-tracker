import { useState } from 'react'
import { X, Plus, Trash2, RefreshCw, ExternalLink } from 'lucide-react'

function formatDateTime(iso) {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function thirtyDaysAgo() {
  const d = new Date()
  d.setDate(d.getDate() - 30)
  return d.toISOString().slice(0, 10)
}

function today() {
  return new Date().toISOString().slice(0, 10)
}

export default function BankConnectModal({ connections, onClose, onConnect, onDelete, onSync }) {
  const [provider, setProvider] = useState('psd2')
  const [label, setLabel] = useState('')
  const [userCode, setUserCode] = useState('')
  const [password, setPassword] = useState('')
  const [otpCode, setOtpCode] = useState('')
  const [needsOtp, setNeedsOtp] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [syncingId, setSyncingId] = useState(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)

  function resetForm() {
    setLabel('')
    setUserCode('')
    setPassword('')
    setOtpCode('')
    setNeedsOtp(false)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!label.trim()) return
    setSubmitting(true)
    setError('')
    // Opened synchronously within the click's call stack so Chrome treats it as
    // part of the user gesture — opening it after the `await onConnect` below
    // would arrive too late and get popup-blocked.
    const popup = provider === 'psd2' ? window.open('', '_blank', 'noopener') : null
    try {
      const payload = { provider, label: label.trim() }
      if (provider === 'scraper') {
        payload.user_code = userCode
        payload.password = password
        if (otpCode) payload.otp_code = otpCode
      }
      const connection = await onConnect(payload)
      if (popup && connection.sca_redirect_url) {
        popup.location.href = connection.sca_redirect_url
      } else if (popup) {
        popup.close()
      }
      resetForm()
    } catch (err) {
      if (popup) popup.close()
      const status = err.response?.status
      const detail = err.response?.data?.detail || ''
      if (status === 401 && /otp/i.test(detail)) {
        setNeedsOtp(true)
        setError('Enter the one-time code sent by your bank.')
      } else {
        setError(detail || 'Could not connect. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSync(connection) {
    setSyncingId(connection.id)
    setError('')
    try {
      await onSync(connection.id, thirtyDaysAgo(), today())
    } catch (err) {
      setError(err.response?.data?.detail || 'Sync failed.')
    } finally {
      setSyncingId(null)
    }
  }

  async function handleDelete(connection) {
    try {
      await onDelete(connection.id)
      setConfirmDeleteId(null)
    } catch {
      setError('Could not remove connection.')
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Bank Connections</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {!connections.length && (
          <div className="empty-state">No bank accounts connected yet.</div>
        )}

        {connections.length > 0 && (
          <div className="recurring-bills-list">
            {connections.map((c) => (
              <div key={c.id}>
                <div className="recurring-bill-row">
                  <div className="recurring-bill-main">
                    <div className="recurring-bill-top">
                      <span className="recurring-bill-name">{c.label}</span>
                      <span className={`bank-status-badge bank-status-${c.status}`}>{c.status}</span>
                    </div>
                    <div className="recurring-bill-schedule">
                      {c.provider === 'psd2' ? 'Open Banking (PSD2)' : 'Bank scraper'} · Last synced:{' '}
                      {formatDateTime(c.last_synced_at)}
                    </div>
                    {c.last_error && <div className="category-manager-error">{c.last_error}</div>}
                  </div>
                  <button
                    className="icon-btn"
                    onClick={() => handleSync(c)}
                    disabled={syncingId === c.id || c.status !== 'valid'}
                    aria-label="Sync now"
                  >
                    <RefreshCw size={16} className={syncingId === c.id ? 'spin' : ''} />
                  </button>
                  <button
                    className="delete-btn"
                    onClick={() => setConfirmDeleteId(c.id)}
                    aria-label="Remove connection"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                {confirmDeleteId === c.id && (
                  <div className="recurring-bill-confirm">
                    <p>Remove "{c.label}"? Already-imported expenses will be kept.</p>
                    <div className="add-category-row">
                      <button className="inline-btn primary" onClick={() => handleDelete(c)}>
                        Yes, remove
                      </button>
                      <button className="inline-btn" onClick={() => setConfirmDeleteId(null)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="add-category-footer">
          <h3 className="card-title">Connect a Bank Account</h3>
          <form className="expense-form" onSubmit={handleSubmit}>
            <div className="form-field">
              <label htmlFor="bank-label">Label</label>
              <input
                id="bank-label"
                type="text"
                placeholder="e.g. Hapoalim Checking"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                required
              />
            </div>

            <div className="form-field">
              <label htmlFor="bank-provider">Method</label>
              <select
                id="bank-provider"
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value)
                  setNeedsOtp(false)
                  setError('')
                }}
              >
                <option value="psd2">Open Banking (PSD2) — official, requires a licensed connection</option>
                <option value="scraper">Direct login (israeli-bank-scrapers)</option>
              </select>
            </div>

            {provider === 'psd2' && (
              <p className="category-manager-error" style={{ color: 'var(--color-text-muted)' }}>
                Opens your bank's consent page in a new tab. Requires production PSD2 credentials
                configured on the server.
              </p>
            )}

            {provider === 'scraper' && (
              <>
                <div className="form-row">
                  <div className="form-field">
                    <label htmlFor="bank-usercode">ID number</label>
                    <input
                      id="bank-usercode"
                      type="text"
                      value={userCode}
                      onChange={(e) => setUserCode(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-field">
                    <label htmlFor="bank-password">Password</label>
                    <input
                      id="bank-password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                    />
                  </div>
                </div>
                {needsOtp && (
                  <div className="form-field">
                    <label htmlFor="bank-otp">One-time code</label>
                    <input
                      id="bank-otp"
                      type="text"
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value)}
                      autoFocus
                    />
                  </div>
                )}
              </>
            )}

            <button type="submit" className="submit-btn" disabled={submitting}>
              {provider === 'psd2' ? <ExternalLink size={18} /> : <Plus size={18} />}
              {provider === 'psd2' ? 'Start Consent' : needsOtp ? 'Confirm Code' : 'Connect'}
            </button>

            {error && <div className="error-banner">{error}</div>}
          </form>
        </div>
      </div>
    </div>
  )
}
