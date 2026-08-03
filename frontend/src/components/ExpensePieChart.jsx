import { useState } from 'react'
import { Pencil } from 'lucide-react'
import { PieChart, Pie, Cell, Legend, Tooltip, ResponsiveContainer } from 'recharts'

export default function ExpensePieChart({ summary }) {
  const [label, setLabel] = useState('total this month')
  const [editingLabel, setEditingLabel] = useState(false)
  const [labelDraft, setLabelDraft] = useState(label)

  if (!summary || !summary.categories?.length) {
    return (
      <div className="card">
        <h2 className="card-title">Spending Breakdown</h2>
        <div className="chart-empty">No expenses yet this month.</div>
      </div>
    )
  }

  const data = summary.categories.map((c) => ({
    name: c.name,
    value: c.amount,
    percent: c.percent,
    color: c.color,
  }))

  const pendingSettlement = summary.pending_settlement || 0
  const alreadySpent = summary.total - pendingSettlement

  function startEditLabel() {
    setLabelDraft(label)
    setEditingLabel(true)
  }

  function saveLabel() {
    if (labelDraft.trim()) setLabel(labelDraft.trim())
    setEditingLabel(false)
  }

  return (
    <div className="card">
      <h2 className="card-title">Spending Breakdown</h2>
      <div className="summary-total">
        <div className="summary-total-amount">₪{summary.total.toFixed(2)}</div>
        {editingLabel ? (
          <input
            className="summary-total-label-input"
            value={labelDraft}
            onChange={(e) => setLabelDraft(e.target.value)}
            onBlur={saveLabel}
            onKeyDown={(e) => {
              if (e.key === 'Enter') saveLabel()
              if (e.key === 'Escape') setEditingLabel(false)
            }}
            autoFocus
          />
        ) : (
          <button className="summary-total-label" onClick={startEditLabel}>
            {label}
            <Pencil size={12} />
          </button>
        )}
        {pendingSettlement > 0 && (
          <div className="summary-settlement-breakdown">
            <span>₪{alreadySpent.toFixed(2)} already left your account</span>
            <span>₪{pendingSettlement.toFixed(2)} due by the 10th</span>
          </div>
        )}
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={85}
            paddingAngle={2}
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value, name, props) => [
              `₪${value.toFixed(2)} (${props.payload.percent.toFixed(1)}%)`,
              name,
            ]}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
