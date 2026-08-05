import { useState } from 'react'
import { Trash2, ChevronDown, ChevronUp } from 'lucide-react'

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function ExpenseRow({ exp, categories, onDelete, onRecategorize }) {
  const [categoryId, setCategoryId] = useState(exp.category_id)
  const [saving, setSaving] = useState(false)

  const dotColor = categories.find((c) => c.id === categoryId)?.color ?? exp.category_color

  async function handleChange(e) {
    const next = Number(e.target.value)
    const previous = categoryId
    setCategoryId(next)
    setSaving(true)
    try {
      await onRecategorize(exp.id, next)
    } catch {
      setCategoryId(previous)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="expense-row">
      <div className="expense-row-main">
        <div className="expense-row-top">
          <span className="color-dot" style={{ background: dotColor }} />
          <select
            className="expense-category-select"
            value={categoryId ?? ''}
            onChange={handleChange}
            disabled={saving || exp.is_rent}
            aria-label="Category"
          >
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.name}
              </option>
            ))}
          </select>
        </div>
        <div className="expense-row-date">{formatDate(exp.date)}</div>
        {exp.note && <div className="expense-row-note">{exp.note}</div>}
      </div>
      <div className="expense-row-amount">₪{exp.amount.toFixed(2)}</div>
      <button className="delete-btn" onClick={() => onDelete(exp.id)} aria-label="Delete expense">
        <Trash2 size={16} />
      </button>
    </div>
  )
}

function CollapsibleGroup({
  title,
  items,
  categories,
  onDelete,
  onRecategorize,
  emptyText,
  defaultExpanded,
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  return (
    <div className="card">
      <button
        className="card-title expense-list-toggle"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        {title}
        <span className="expense-list-count">({items.length})</span>
        {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>
      <div className="expense-list" hidden={!expanded}>
        {items.length === 0 && <div className="empty-state">{emptyText}</div>}
        {items.map((exp) => (
          <ExpenseRow
            key={exp.id}
            exp={exp}
            categories={categories}
            onDelete={onDelete}
            onRecategorize={onRecategorize}
          />
        ))}
      </div>
    </div>
  )
}

export default function ExpenseList({ expenses, categories, onDelete, onRecategorize }) {
  if (!expenses.length) {
    return (
      <div className="card">
        <h2 className="card-title">Expenses</h2>
        <div className="empty-state">
          <div className="empty-state-emoji">🧾</div>
          No expenses logged for this month yet.
          <br />
          Sync a bank connection from the bank icon in the header to import them.
        </div>
      </div>
    )
  }

  const sortFn = (a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : b.id - a.id)
  const rent = expenses.filter((e) => e.is_rent).sort(sortFn)
  const direct = expenses.filter((e) => e.bank_txn_id && e.settlement === 'immediate').sort(sortFn)
  const delayed = expenses.filter((e) => e.bank_txn_id && e.settlement === 'delayed').sort(sortFn)
  const other = expenses.filter((e) => !e.is_rent && !e.bank_txn_id).sort(sortFn)

  return (
    <>
      <CollapsibleGroup
        title="Rent"
        items={rent}
        categories={categories}
        onDelete={onDelete}
        onRecategorize={onRecategorize}
        emptyText="No rent expense for this month."
        defaultExpanded={false}
      />
      {direct.length > 0 && (
        <CollapsibleGroup
          title="Direct Charges"
          items={direct}
          categories={categories}
          onDelete={onDelete}
          onRecategorize={onRecategorize}
          emptyText="No direct charges for this month."
          defaultExpanded={true}
        />
      )}
      {delayed.length > 0 && (
        <CollapsibleGroup
          title="Delayed Charges"
          items={delayed}
          categories={categories}
          onDelete={onDelete}
          onRecategorize={onRecategorize}
          emptyText="No delayed charges for this month."
          defaultExpanded={true}
        />
      )}
      {other.length > 0 && (
        <CollapsibleGroup
          title="Other Expenses"
          items={other}
          categories={categories}
          onDelete={onDelete}
          onRecategorize={onRecategorize}
          emptyText="No one-off expenses logged for this month yet."
          defaultExpanded={false}
        />
      )}
    </>
  )
}
