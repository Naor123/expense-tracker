import { ChevronLeft, ChevronRight } from 'lucide-react'

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

function formatMonthLabel(month) {
  const [year, m] = month.split('-').map(Number)
  return `${MONTH_NAMES[m - 1]} ${year}`
}

function shiftMonth(month, delta) {
  const [year, m] = month.split('-').map(Number)
  const date = new Date(year, m - 1 + delta, 1)
  const newMonth = String(date.getMonth() + 1).padStart(2, '0')
  return `${date.getFullYear()}-${newMonth}`
}

export default function MonthPicker({ month, onChange }) {
  return (
    <div className="month-picker">
      <button
        className="icon-btn"
        onClick={() => onChange(shiftMonth(month, -1))}
        aria-label="Previous month"
      >
        <ChevronLeft size={20} />
      </button>
      <span className="month-picker-label">{formatMonthLabel(month)}</span>
      <button
        className="icon-btn"
        onClick={() => onChange(shiftMonth(month, 1))}
        aria-label="Next month"
      >
        <ChevronRight size={20} />
      </button>
    </div>
  )
}
