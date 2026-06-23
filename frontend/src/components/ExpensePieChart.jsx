import { PieChart, Pie, Cell, Legend, Tooltip, ResponsiveContainer } from 'recharts'

export default function ExpensePieChart({ summary }) {
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

  return (
    <div className="card">
      <h2 className="card-title">Spending Breakdown</h2>
      <div className="summary-total">
        <div className="summary-total-amount">₪{summary.total.toFixed(2)}</div>
        <div className="summary-total-label">total this month</div>
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
