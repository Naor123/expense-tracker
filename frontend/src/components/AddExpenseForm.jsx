import { useState } from 'react'
import { Plus, Check } from 'lucide-react'

function defaultDateForMonth(month) {
  const today = new Date()
  const todayMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  if (todayMonth === month) {
    return today.toISOString().slice(0, 10)
  }
  return `${month}-01`
}

export default function AddExpenseForm({ month, categories, onAddExpense, onAddCategory }) {
  const [amount, setAmount] = useState('')
  const [categoryId, setCategoryId] = useState(categories[0]?.id ?? '')
  const [date, setDate] = useState(() => defaultDateForMonth(month))
  const [note, setNote] = useState('')
  const [showAddCategory, setShowAddCategory] = useState(false)
  const [newCategoryName, setNewCategoryName] = useState('')
  const [newCategoryColor, setNewCategoryColor] = useState('#4f46e5')
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  const effectiveCategoryId = categoryId || categories[0]?.id || ''

  function handleCategoryChange(e) {
    if (e.target.value === '__add__') {
      setShowAddCategory(true)
    } else {
      setCategoryId(e.target.value)
    }
  }

  async function handleCreateCategory() {
    if (!newCategoryName.trim()) return
    try {
      const created = await onAddCategory(newCategoryName.trim(), newCategoryColor)
      setCategoryId(created.id)
      setNewCategoryName('')
      setNewCategoryColor('#4f46e5')
      setShowAddCategory(false)
      setError('')
    } catch (err) {
      setError(err.response?.status === 409 ? 'Category name already exists.' : 'Could not create category.')
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!amount || Number(amount) <= 0 || !effectiveCategoryId) return
    setSubmitting(true)
    setError('')
    try {
      await onAddExpense({
        amount: Number(amount),
        category_id: effectiveCategoryId,
        date,
        note: note.trim() || undefined,
      })
      setAmount('')
      setNote('')
      setDate(defaultDateForMonth(month))
      setSuccess(true)
      setTimeout(() => setSuccess(false), 2000)
    } catch {
      setError('Could not add expense. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="card">
      <h2 className="card-title">Add Expense</h2>
      <form className="expense-form" onSubmit={handleSubmit}>
        <div className="form-row">
          <div className="form-field form-field-amount">
            <label htmlFor="amount">Amount</label>
            <input
              id="amount"
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
            <label htmlFor="category">Category</label>
            <select id="category" value={effectiveCategoryId} onChange={handleCategoryChange}>
              {categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
              <option value="__add__">+ Add category</option>
            </select>
          </div>
          <div className="form-field form-field-date">
            <label htmlFor="date">Date</label>
            <input
              id="date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
            />
          </div>
        </div>

        {showAddCategory && (
          <div className="add-category-inline">
            <div className="add-category-row">
              <input
                type="text"
                placeholder="Category name"
                value={newCategoryName}
                onChange={(e) => setNewCategoryName(e.target.value)}
              />
              <input
                type="color"
                value={newCategoryColor}
                onChange={(e) => setNewCategoryColor(e.target.value)}
              />
            </div>
            <div className="add-category-row">
              <button type="button" className="inline-btn primary" onClick={handleCreateCategory}>
                <Check size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                Save category
              </button>
              <button type="button" className="inline-btn" onClick={() => setShowAddCategory(false)}>
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="form-field">
          <label htmlFor="note">Note (optional)</label>
          <input
            id="note"
            type="text"
            placeholder="e.g. groceries at Shufersal"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>

        <button type="submit" className="submit-btn" disabled={submitting}>
          <Plus size={18} />
          Add Expense
        </button>

        {success && (
          <div className="success-banner">
            <Check size={14} />
            Expense added
          </div>
        )}
        {error && <div className="error-banner">{error}</div>}
      </form>
    </div>
  )
}
