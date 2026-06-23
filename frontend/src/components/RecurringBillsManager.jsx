import { useState, useEffect } from 'react'
import { X, Plus, Trash2, Check, Pencil } from 'lucide-react'

const ODD_MONTHS = 'Jan, Mar, May, Jul, Sep, Nov'
const EVEN_MONTHS = 'Feb, Apr, Jun, Aug, Oct, Dec'

function scheduleLabel(bill) {
  if (bill.interval_months === 2) {
    return bill.month_parity === 'odd'
      ? `Every 2 months — odd months (${ODD_MONTHS})`
      : `Every 2 months — even months (${EVEN_MONTHS})`
  }
  return 'Every month'
}

function currentMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export default function RecurringBillsManager({
  bills,
  categories,
  onClose,
  onCreate,
  onUpdate,
  onDelete,
}) {
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [categoryId, setCategoryId] = useState(categories[0]?.id ?? '')
  const [schedule, setSchedule] = useState('monthly')
  const [startMonth, setStartMonth] = useState(currentMonth())
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editAmount, setEditAmount] = useState('')
  const [editApplyScope, setEditApplyScope] = useState('current')

  useEffect(() => {
    if (!categoryId && categories[0]) setCategoryId(categories[0].id)
  }, [categories, categoryId])

  const effectiveCategoryId = categoryId || categories[0]?.id || ''

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim() || !amount || Number(amount) <= 0 || !effectiveCategoryId) return
    setSubmitting(true)
    setError('')
    try {
      const payload = {
        name: name.trim(),
        amount: Number(amount),
        category_id: effectiveCategoryId,
        start_month: startMonth,
      }
      if (schedule === 'odd') {
        payload.interval_months = 2
        payload.month_parity = 'odd'
      } else if (schedule === 'even') {
        payload.interval_months = 2
        payload.month_parity = 'even'
      } else {
        payload.interval_months = 1
      }
      await onCreate(payload)
      setName('')
      setAmount('')
      setSchedule('monthly')
      setStartMonth(currentMonth())
      setSuccess(true)
      setTimeout(() => setSuccess(false), 2000)
    } catch {
      setError('Could not create recurring bill. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleToggleActive(bill) {
    try {
      await onUpdate(bill.id, { active: !bill.active })
    } catch {
      setError('Could not update bill.')
    }
  }

  async function handleDelete(bill) {
    try {
      await onDelete(bill.id)
      setConfirmDeleteId(null)
    } catch {
      setError('Could not delete bill.')
    }
  }

  function startEdit(bill) {
    setEditingId(bill.id)
    setEditAmount(String(bill.amount))
    setEditApplyScope('current')
    setConfirmDeleteId(null)
  }

  async function handleSaveEdit(bill) {
    if (!editAmount || Number(editAmount) <= 0) return
    try {
      await onUpdate(bill.id, {
        amount: Number(editAmount),
        apply_amount_to: editApplyScope,
      })
      setEditingId(null)
    } catch {
      setError('Could not update price.')
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Recurring Bills</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {!bills.length && (
          <div className="empty-state">
            No recurring bills yet.
            <br />
            Add one below to auto-generate it every month.
          </div>
        )}

        {bills.length > 0 && (
          <div className="recurring-bills-list">
            {bills.map((bill) => (
              <div key={bill.id}>
                <div className="recurring-bill-row">
                  <div className="recurring-bill-main">
                    <div className="recurring-bill-top">
                      <span className="color-dot" style={{ background: bill.category_color }} />
                      <span className="recurring-bill-name">{bill.name}</span>
                      <span className="recurring-bill-amount">₪{bill.amount.toFixed(2)}</span>
                    </div>
                    <div className="recurring-bill-schedule">{scheduleLabel(bill)}</div>
                  </div>
                  <button
                    className="icon-btn"
                    onClick={() => (editingId === bill.id ? setEditingId(null) : startEdit(bill))}
                    aria-label="Edit price"
                  >
                    <Pencil size={16} />
                  </button>
                  <label className="toggle-switch" aria-label={bill.active ? 'Pause bill' : 'Resume bill'}>
                    <input
                      type="checkbox"
                      checked={bill.active}
                      onChange={() => handleToggleActive(bill)}
                    />
                    <span className="toggle-slider" />
                  </label>
                  <button
                    className="delete-btn"
                    onClick={() => setConfirmDeleteId(bill.id)}
                    aria-label="Delete recurring bill"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                {editingId === bill.id && (
                  <div className="recurring-bill-edit">
                    <div className="form-field">
                      <label htmlFor={`edit-amount-${bill.id}`}>New amount</label>
                      <input
                        id={`edit-amount-${bill.id}`}
                        type="number"
                        min="0.01"
                        step="0.01"
                        inputMode="decimal"
                        value={editAmount}
                        onChange={(e) => setEditAmount(e.target.value)}
                        autoFocus
                      />
                    </div>
                    <div className="recurring-bill-edit-scope">
                      <label>
                        <input
                          type="radio"
                          name={`apply-scope-${bill.id}`}
                          value="current"
                          checked={editApplyScope === 'current'}
                          onChange={() => setEditApplyScope('current')}
                        />
                        From this month onward only
                      </label>
                      <label>
                        <input
                          type="radio"
                          name={`apply-scope-${bill.id}`}
                          value="all"
                          checked={editApplyScope === 'all'}
                          onChange={() => setEditApplyScope('all')}
                        />
                        From this month onward, and update past months too
                      </label>
                    </div>
                    <div className="add-category-row">
                      <button className="inline-btn primary" onClick={() => handleSaveEdit(bill)}>
                        <Check size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                        Save
                      </button>
                      <button className="inline-btn" onClick={() => setEditingId(null)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
                {confirmDeleteId === bill.id && (
                  <div className="recurring-bill-confirm">
                    <p>
                      Stop "{bill.name}" from auto-generating future expenses? Past expenses
                      already created from it will NOT be removed.
                    </p>
                    <div className="add-category-row">
                      <button className="inline-btn primary" onClick={() => handleDelete(bill)}>
                        Yes, stop it
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
          <h3 className="card-title">Add Recurring Bill</h3>
          <form className="expense-form" onSubmit={handleSubmit}>
            <div className="form-field">
              <label htmlFor="rb-name">Name</label>
              <input
                id="rb-name"
                type="text"
                placeholder="e.g. Rent"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>

            <div className="form-row">
              <div className="form-field">
                <label htmlFor="rb-amount">Amount</label>
                <input
                  id="rb-amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  required
                />
              </div>
              <div className="form-field">
                <label htmlFor="rb-category">Category</label>
                <select
                  id="rb-category"
                  value={effectiveCategoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                >
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.id}>
                      {cat.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-field">
              <label htmlFor="rb-schedule">Schedule</label>
              <select id="rb-schedule" value={schedule} onChange={(e) => setSchedule(e.target.value)}>
                <option value="monthly">Every month</option>
                <option value="odd">Every 2 months (odd months: {ODD_MONTHS})</option>
                <option value="even">Every 2 months (even months: {EVEN_MONTHS})</option>
              </select>
            </div>

            <div className="form-field">
              <label htmlFor="rb-start">Start month</label>
              <input
                id="rb-start"
                type="month"
                value={startMonth}
                onChange={(e) => setStartMonth(e.target.value)}
                required
              />
            </div>

            <button type="submit" className="submit-btn" disabled={submitting}>
              <Plus size={18} />
              Add Recurring Bill
            </button>

            {success && (
              <div className="success-banner">
                <Check size={14} />
                Recurring bill added
              </div>
            )}
            {error && <div className="error-banner">{error}</div>}
          </form>
        </div>
      </div>
    </div>
  )
}
