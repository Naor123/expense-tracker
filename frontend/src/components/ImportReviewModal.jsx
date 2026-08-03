import { useState } from 'react'
import { X, Check, XCircle, AlertTriangle } from 'lucide-react'

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export default function ImportReviewModal({ transactions, categories, onClose, onApprove, onIgnore, onBulkApprove }) {
  const [selectedCategory, setSelectedCategory] = useState({})
  const [saveRule, setSaveRule] = useState({})
  const [checked, setChecked] = useState({})
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState('')

  function categoryFor(txn) {
    return selectedCategory[txn.id] ?? txn.suggested_category_id ?? categories[0]?.id ?? ''
  }

  async function handleApprove(txn) {
    setBusyId(txn.id)
    setError('')
    try {
      await onApprove(txn.id, {
        category_id: Number(categoryFor(txn)),
        save_rule: !!saveRule[txn.id],
        rule_pattern: txn.counterparty,
      })
    } catch {
      setError('Could not approve transaction.')
    } finally {
      setBusyId(null)
    }
  }

  async function handleIgnore(txn) {
    setBusyId(txn.id)
    setError('')
    try {
      await onIgnore(txn.id)
    } catch {
      setError('Could not ignore transaction.')
    } finally {
      setBusyId(null)
    }
  }

  async function handleBulkApprove() {
    const ids = Object.keys(checked)
      .filter((id) => checked[id])
      .map(Number)
    if (!ids.length) return
    setError('')
    try {
      await onBulkApprove(ids)
      setChecked({})
    } catch {
      setError('Could not approve selected transactions.')
    }
  }

  const anyChecked = Object.values(checked).some(Boolean)

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Review Imported Transactions</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {!transactions.length && (
          <div className="empty-state">
            No pending transactions. Sync a connected bank account to import new ones.
          </div>
        )}

        {transactions.length > 0 && (
          <>
            <div className="add-category-row">
              <button className="inline-btn primary" onClick={handleBulkApprove} disabled={!anyChecked}>
                <Check size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                Approve Selected
              </button>
            </div>

            <div className="recurring-bills-list">
              {transactions.map((txn) => (
                <div key={txn.id} className="recurring-bill-row">
                  <input
                    type="checkbox"
                    checked={!!checked[txn.id]}
                    onChange={(e) => setChecked((prev) => ({ ...prev, [txn.id]: e.target.checked }))}
                    aria-label="Select for bulk approve"
                  />
                  <div className="recurring-bill-main">
                    <div className="recurring-bill-top">
                      <span className="recurring-bill-name">{txn.counterparty || 'Unknown'}</span>
                      <span className="recurring-bill-amount">₪{Math.abs(txn.amount).toFixed(2)}</span>
                      {txn.possible_duplicate && (
                        <span className="bank-duplicate-badge" title="Matches an active recurring bill amount">
                          <AlertTriangle size={12} /> possible duplicate
                        </span>
                      )}
                    </div>
                    <div className="recurring-bill-schedule">
                      {formatDate(txn.booking_date)}
                      {txn.description ? ` · ${txn.description}` : ''}
                    </div>
                    <div className="add-category-row" style={{ marginTop: 6 }}>
                      <select
                        value={categoryFor(txn)}
                        onChange={(e) =>
                          setSelectedCategory((prev) => ({ ...prev, [txn.id]: e.target.value }))
                        }
                      >
                        {categories.map((cat) => (
                          <option key={cat.id} value={cat.id}>
                            {cat.name}
                          </option>
                        ))}
                      </select>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.85rem' }}>
                        <input
                          type="checkbox"
                          checked={!!saveRule[txn.id]}
                          onChange={(e) => setSaveRule((prev) => ({ ...prev, [txn.id]: e.target.checked }))}
                        />
                        Remember for "{txn.counterparty}"
                      </label>
                    </div>
                  </div>
                  <button
                    className="icon-btn"
                    onClick={() => handleApprove(txn)}
                    disabled={busyId === txn.id}
                    aria-label="Approve"
                  >
                    <Check size={16} />
                  </button>
                  <button
                    className="delete-btn"
                    onClick={() => handleIgnore(txn)}
                    disabled={busyId === txn.id}
                    aria-label="Ignore"
                  >
                    <XCircle size={16} />
                  </button>
                </div>
              ))}
            </div>
          </>
        )}

        {error && <div className="error-banner">{error}</div>}
      </div>
    </div>
  )
}
