import { useState } from 'react'
import { X, Check, XCircle, AlertTriangle, Landmark, CreditCard, Clock, Wallet } from 'lucide-react'

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const KIND_INFO = {
  bank_transfer: { label: 'Bank Transfer', Icon: Landmark },
  credit_card_charge: { label: 'Card Purchase', Icon: CreditCard },
  credit_card_payment: { label: 'Card Payment', Icon: CreditCard },
}

const SOURCE_LABELS = {
  hapoalim: 'Hapoalim',
  max: 'Max',
}

export default function ImportReviewModal({
  transactions,
  categories,
  onClose,
  onApprove,
  onIgnore,
  onBulkApprove,
  onMarkSalary,
}) {
  const [selectedCategory, setSelectedCategory] = useState({})
  const [saveRule, setSaveRule] = useState({})
  const [checked, setChecked] = useState({})
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState('')
  const [salaryRule, setSalaryRule] = useState({})

  const pendingSettlementTotal = transactions
    .filter((t) => t.kind === 'credit_card_charge' && t.settlement === 'delayed')
    .reduce((sum, t) => sum + Math.abs(t.amount), 0)
  const latestSettlementDate = transactions
    .filter((t) => t.kind === 'credit_card_charge' && t.settlement === 'delayed' && t.value_date)
    .map((t) => t.value_date)
    .sort()
    .pop()

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

  async function handleMarkSalary(txn) {
    setBusyId(txn.id)
    setError('')
    try {
      await onMarkSalary(txn.id, !!salaryRule[txn.id])
    } catch {
      setError('Could not mark as salary.')
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
            {pendingSettlementTotal > 0 && (
              <div className="category-manager-error" style={{ color: 'var(--color-text-muted)' }}>
                <Clock size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                ₪{pendingSettlementTotal.toFixed(2)} still pending settlement
                {latestSettlementDate ? `, by ${formatDate(latestSettlementDate)}` : ''}
              </div>
            )}

            <div className="add-category-row">
              <button className="inline-btn primary" onClick={handleBulkApprove} disabled={!anyChecked}>
                <Check size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                Approve Selected
              </button>
            </div>

            <div className="recurring-bills-list">
              {transactions.map((txn) => {
                const isIncomingCredit = txn.amount > 0
                return (
                  <div key={txn.id} className="recurring-bill-row">
                    {!isIncomingCredit && (
                      <input
                        type="checkbox"
                        checked={!!checked[txn.id]}
                        onChange={(e) => setChecked((prev) => ({ ...prev, [txn.id]: e.target.checked }))}
                        aria-label="Select for bulk approve"
                      />
                    )}
                    <div className="recurring-bill-main">
                      <div className="recurring-bill-top">
                        <span className="recurring-bill-name">{txn.counterparty || 'Unknown'}</span>
                        <span className="recurring-bill-amount">₪{Math.abs(txn.amount).toFixed(2)}</span>
                        {(() => {
                          const info = KIND_INFO[txn.kind]
                          if (!info) return null
                          const { label, Icon } = info
                          return (
                            <span className={`bank-kind-badge bank-kind-${txn.kind}`}>
                              <Icon size={12} /> {label}
                            </span>
                          )
                        })()}
                        {txn.kind === 'credit_card_charge' && txn.settlement === 'delayed' && (
                          <span className="bank-settlement-badge" title="Settles as part of next month's card lump sum">
                            <Clock size={12} /> Settles {formatDate(txn.value_date)}
                          </span>
                        )}
                        {txn.possible_duplicate && (
                          <span className="bank-duplicate-badge" title="Matches an active recurring bill amount">
                            <AlertTriangle size={12} /> possible duplicate
                          </span>
                        )}
                      </div>
                      <div className="recurring-bill-schedule">
                        {SOURCE_LABELS[txn.connection_company_id] || txn.connection_label || 'Unknown source'}
                        {' · '}
                        {formatDate(txn.booking_date)}
                        {txn.description ? ` · ${txn.description}` : ''}
                      </div>
                      {isIncomingCredit ? (
                        <div className="bank-salary-actions" style={{ marginTop: 6 }}>
                          <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.85rem' }}>
                            <input
                              type="checkbox"
                              checked={!!salaryRule[txn.id]}
                              onChange={(e) =>
                                setSalaryRule((prev) => ({ ...prev, [txn.id]: e.target.checked }))
                              }
                            />
                            Remember "{txn.counterparty}" as my salary source
                          </label>
                        </div>
                      ) : (
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
                      )}
                    </div>
                    {isIncomingCredit ? (
                      <button
                        className="icon-btn"
                        onClick={() => handleMarkSalary(txn)}
                        disabled={busyId === txn.id}
                        aria-label="Mark as salary"
                        title="Mark as salary"
                      >
                        <Wallet size={16} />
                      </button>
                    ) : (
                      <button
                        className="icon-btn"
                        onClick={() => handleApprove(txn)}
                        disabled={busyId === txn.id}
                        aria-label="Approve"
                      >
                        <Check size={16} />
                      </button>
                    )}
                    <button
                      className="delete-btn"
                      onClick={() => handleIgnore(txn)}
                      disabled={busyId === txn.id}
                      aria-label="Ignore"
                    >
                      <XCircle size={16} />
                    </button>
                  </div>
                )
              })}
            </div>
          </>
        )}

        {error && <div className="error-banner">{error}</div>}
      </div>
    </div>
  )
}
