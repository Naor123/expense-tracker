import { useState } from 'react'
import { X, Landmark, CreditCard, Clock, RotateCcw, Wallet } from 'lucide-react'

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

const IGNORE_REASONS = {
  card_lump_sum: 'Already itemized as individual card charges',
  rent_duplicate: 'Rent is tracked separately',
  itemized_duplicate: 'Same charge already imported from the card',
  incoming_credit: 'Incoming credit, not this month’s salary',
  card_refund: 'Card refund',
  user_deleted: 'You deleted this',
  legacy: 'Ignored before auto-import',
}

function ignoreReasonText(reason) {
  return IGNORE_REASONS[reason] || 'Ignored'
}

function KindBadge({ txn }) {
  const info = KIND_INFO[txn.kind]
  if (!info) return null
  const { label, Icon } = info
  return (
    <span className={`bank-kind-badge bank-kind-${txn.kind}`}>
      <Icon size={12} /> {label}
    </span>
  )
}

function sourceLine(txn) {
  const source = SOURCE_LABELS[txn.connection_company_id] || txn.connection_label || 'Unknown source'
  return `${source} · ${formatDate(txn.booking_date)}${txn.description ? ` · ${txn.description}` : ''}`
}

export default function ImportActivityModal({ transactions, onRestore, onClose }) {
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState('')

  const salaryTxns = transactions.filter((t) => t.status === 'salary')
  const imported = transactions.filter((t) => t.status === 'imported')
  const ignored = transactions.filter((t) => t.status === 'ignored')

  const uncategorized = imported.filter((t) => t.current_category_name === 'Uncategorized')
  const categorized = imported.filter((t) => t.current_category_name !== 'Uncategorized')

  const pendingSettlementTotal = imported
    .filter((t) => t.kind === 'credit_card_charge' && t.settlement === 'delayed')
    .reduce((sum, t) => sum + Math.abs(t.amount), 0)
  const latestSettlementDate = imported
    .filter((t) => t.kind === 'credit_card_charge' && t.settlement === 'delayed' && t.value_date)
    .map((t) => t.value_date)
    .sort()
    .pop()

  async function handleRestore(txn) {
    setBusyId(txn.id)
    setError('')
    try {
      await onRestore(txn.id)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not restore transaction.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Import Activity</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {!transactions.length && (
          <div className="empty-state">
            Nothing imported for this month yet. Sync a connected bank account from the bank icon in
            the header.
          </div>
        )}

        {salaryTxns.length > 0 && (
          <>
            <h3 className="card-title">Salary</h3>
            <div className="recurring-bills-list">
              {salaryTxns.map((txn) => (
                <div key={txn.id} className="import-activity-salary">
                  <Wallet size={16} />
                  <span>
                    Salary detected: ₪{Math.abs(txn.amount).toFixed(2)} from{' '}
                    {txn.counterparty || 'Unknown'} · {formatDate(txn.booking_date)}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}

        {uncategorized.length > 0 && (
          <>
            <h3 className="card-title">Uncategorized</h3>
            <div className="recurring-bills-list">
              {uncategorized.map((txn) => (
                <div key={txn.id} className="recurring-bill-row bank-uncategorized-row">
                  <div className="recurring-bill-main">
                    <div className="recurring-bill-top">
                      <span className="recurring-bill-name">{txn.counterparty || 'Unknown'}</span>
                      <span className="recurring-bill-amount">₪{Math.abs(txn.amount).toFixed(2)}</span>
                      <KindBadge txn={txn} />
                      {txn.kind === 'credit_card_charge' && txn.settlement === 'delayed' && (
                        <span
                          className="bank-settlement-badge"
                          title="Settles as part of next month's card lump sum"
                        >
                          <Clock size={12} /> Settles {formatDate(txn.value_date)}
                        </span>
                      )}
                    </div>
                    <div className="recurring-bill-schedule">{sourceLine(txn)}</div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {categorized.length > 0 && (
          <>
            <h3 className="card-title">Imported</h3>
            {pendingSettlementTotal > 0 && (
              <div className="category-manager-error" style={{ color: 'var(--color-text-muted)' }}>
                <Clock size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                ₪{pendingSettlementTotal.toFixed(2)} still pending settlement
                {latestSettlementDate ? `, by ${formatDate(latestSettlementDate)}` : ''}
              </div>
            )}
            <div className="recurring-bills-list">
              {categorized.map((txn) => (
                <div key={txn.id} className="recurring-bill-row">
                  <div className="recurring-bill-main">
                    <div className="recurring-bill-top">
                      <span className="recurring-bill-name">{txn.counterparty || 'Unknown'}</span>
                      <span className="recurring-bill-amount">₪{Math.abs(txn.amount).toFixed(2)}</span>
                      {txn.current_category_name && (
                        <span className="bank-kind-badge bank-category-badge">
                          {txn.current_category_name}
                        </span>
                      )}
                      <KindBadge txn={txn} />
                      {txn.kind === 'credit_card_charge' && txn.settlement === 'delayed' && (
                        <span
                          className="bank-settlement-badge"
                          title="Settles as part of next month's card lump sum"
                        >
                          <Clock size={12} /> Settles {formatDate(txn.value_date)}
                        </span>
                      )}
                    </div>
                    <div className="recurring-bill-schedule">{sourceLine(txn)}</div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {ignored.length > 0 && (
          <>
            <h3 className="card-title">Ignored</h3>
            <div className="recurring-bills-list">
              {ignored.map((txn) => (
                <div key={txn.id} className="recurring-bill-row">
                  <div className="recurring-bill-main">
                    <div className="recurring-bill-top">
                      <span className="recurring-bill-name">{txn.counterparty || 'Unknown'}</span>
                      <span className="recurring-bill-amount">₪{Math.abs(txn.amount).toFixed(2)}</span>
                      <KindBadge txn={txn} />
                    </div>
                    <div className="recurring-bill-schedule">{sourceLine(txn)}</div>
                    <div className="bank-ignore-reason">{ignoreReasonText(txn.ignore_reason)}</div>
                  </div>
                  <button
                    className="icon-btn"
                    onClick={() => handleRestore(txn)}
                    disabled={busyId === txn.id}
                    aria-label="Restore as expense"
                    title="Restore as expense"
                  >
                    <RotateCcw size={16} className={busyId === txn.id ? 'spin' : ''} />
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
