import { useState } from 'react'
import { Trash2, ChevronDown, ChevronUp } from 'lucide-react'

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function ExpenseRow({ exp, onDelete }) {
  return (
    <div className="expense-row">
      <div className="expense-row-main">
        <div className="expense-row-top">
          <span className="color-dot" style={{ background: exp.category_color }} />
          {exp.category_name}
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

function CollapsibleGroup({ title, items, onDelete, emptyText, defaultExpanded }) {
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
          <ExpenseRow key={exp.id} exp={exp} onDelete={onDelete} />
        ))}
      </div>
    </div>
  )
}

export default function ExpenseList({ expenses, onDelete }) {
  if (!expenses.length) {
    return (
      <div className="card">
        <h2 className="card-title">Expenses</h2>
        <div className="empty-state">
          <div className="empty-state-emoji">🧾</div>
          No expenses logged for this month yet.
          <br />
          Add your first one above.
        </div>
      </div>
    )
  }

  const sortFn = (a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : b.id - a.id)
  const recurring = expenses.filter((e) => e.recurring_id).sort(sortFn)
  const imported = expenses.filter((e) => e.bank_txn_id).sort(sortFn)
  const other = expenses.filter((e) => !e.recurring_id && !e.bank_txn_id).sort(sortFn)

  return (
    <>
      <CollapsibleGroup
        title="Recurring Bills"
        items={recurring}
        onDelete={onDelete}
        emptyText="No recurring bills for this month."
        defaultExpanded={false}
      />
      {imported.length > 0 && (
        <CollapsibleGroup
          title="Imported from Bank"
          items={imported}
          onDelete={onDelete}
          emptyText="No imported transactions for this month."
          defaultExpanded={false}
        />
      )}
      <CollapsibleGroup
        title="Other Expenses"
        items={other}
        onDelete={onDelete}
        emptyText="No one-off expenses logged for this month yet."
        defaultExpanded={false}
      />
    </>
  )
}
