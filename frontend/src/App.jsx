import { useState, useEffect, useCallback } from 'react'
import { Settings, Repeat, Mail, Check } from 'lucide-react'
import MonthPicker from './components/MonthPicker'
import AddExpenseForm from './components/AddExpenseForm'
import ExpensePieChart from './components/ExpensePieChart'
import ExpenseList from './components/ExpenseList'
import CategoryManager from './components/CategoryManager'
import RecurringBillsManager from './components/RecurringBillsManager'
import ThemeToggle from './components/ThemeToggle'
import {
  getCategories,
  createCategory,
  updateCategory,
  deleteCategory,
  getExpenses,
  createExpense,
  deleteExpense,
  getSummary,
  getRecurringBills,
  createRecurringBill,
  updateRecurringBill,
  deleteRecurringBill,
  sendInsightsEmail,
  getSalary,
  updateSalary,
} from './api'

function currentMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light')
  const [month, setMonth] = useState(currentMonth())
  const [categories, setCategories] = useState([])
  const [expenses, setExpenses] = useState([])
  const [summary, setSummary] = useState(null)
  const [showManager, setShowManager] = useState(false)
  const [recurringBills, setRecurringBills] = useState([])
  const [showRecurringManager, setShowRecurringManager] = useState(false)
  const [sendingEmail, setSendingEmail] = useState(false)
  const [emailFeedback, setEmailFeedback] = useState(null)
  const [salary, setSalary] = useState(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const loadMonthData = useCallback(() => {
    return Promise.all([getExpenses(month), getSummary(month)]).then(([exp, sum]) => {
      setExpenses(exp)
      setSummary(sum)
    })
  }, [month])

  useEffect(() => {
    let active = true
    getCategories().then((data) => {
      if (active) setCategories(data)
    })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    getRecurringBills()
      .then((data) => {
        if (active) setRecurringBills(data)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    Promise.all([getExpenses(month), getSummary(month)]).then(([exp, sum]) => {
      if (!active) return
      setExpenses(exp)
      setSummary(sum)
    })
    return () => {
      active = false
    }
  }, [month])

  useEffect(() => {
    let active = true
    getSalary(month).then((data) => {
      if (active) setSalary(data)
    })
    return () => {
      active = false
    }
  }, [month])

  async function handleAddExpense(expense) {
    const created = await createExpense(expense)
    setExpenses((prev) => [...prev, created])
    const sum = await getSummary(month)
    setSummary(sum)
  }

  async function handleDeleteExpense(id) {
    await deleteExpense(id)
    setExpenses((prev) => prev.filter((e) => e.id !== id))
    const sum = await getSummary(month)
    setSummary(sum)
  }

  async function handleAddCategory(name, color) {
    const created = await createCategory(name, color)
    setCategories((prev) => [...prev, created])
    return created
  }

  async function handleUpdateCategory(id, data) {
    const updated = await updateCategory(id, data)
    setCategories((prev) => prev.map((c) => (c.id === id ? updated : c)))
    await loadMonthData()
  }

  async function handleDeleteCategory(id) {
    await deleteCategory(id)
    setCategories((prev) => prev.filter((c) => c.id !== id))
  }

  async function handleCreateRecurringBill(data) {
    const created = await createRecurringBill(data)
    setRecurringBills((prev) => [...prev, created])
    return created
  }

  async function handleUpdateRecurringBill(id, data) {
    const updated = await updateRecurringBill(id, data)
    setRecurringBills((prev) => prev.map((b) => (b.id === id ? updated : b)))
  }

  async function handleDeleteRecurringBill(id) {
    await deleteRecurringBill(id)
    setRecurringBills((prev) => prev.filter((b) => b.id !== id))
  }

  async function handleUpdateSalary(amount) {
    const updated = await updateSalary(month, amount)
    setSalary(updated)
  }

  async function handleSendInsightsEmail() {
    setSendingEmail(true)
    setEmailFeedback(null)
    try {
      const result = await sendInsightsEmail(month)
      setEmailFeedback({ type: 'success', message: `Email sent to ${result.recipient}` })
    } catch (err) {
      const detail = err.response?.data?.detail
      setEmailFeedback({ type: 'error', message: detail || 'Could not send email.' })
    } finally {
      setSendingEmail(false)
      setTimeout(() => setEmailFeedback(null), 4000)
    }
  }

  return (
    <>
      <header className="app-header">
        <h1 className="app-title">Expenses</h1>
        <div className="header-actions">
          <ThemeToggle theme={theme} onToggle={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))} />
          <button
            className="icon-btn"
            onClick={() => setShowRecurringManager(true)}
            aria-label="Manage recurring bills"
          >
            <Repeat size={18} />
          </button>
          <button className="icon-btn" onClick={() => setShowManager(true)} aria-label="Open settings">
            <Settings size={18} />
          </button>
          <button
            className="icon-btn"
            onClick={handleSendInsightsEmail}
            disabled={sendingEmail}
            aria-label="Email this month's insights"
          >
            <Mail size={18} />
          </button>
        </div>
      </header>

      {emailFeedback && (
        <div className={emailFeedback.type === 'success' ? 'success-banner' : 'error-banner'}>
          {emailFeedback.type === 'success' && <Check size={14} />}
          {emailFeedback.message}
        </div>
      )}

      <MonthPicker month={month} onChange={setMonth} />

      <AddExpenseForm
        month={month}
        categories={categories}
        onAddExpense={handleAddExpense}
        onAddCategory={handleAddCategory}
      />

      <ExpensePieChart summary={summary} />

      <ExpenseList expenses={expenses} onDelete={handleDeleteExpense} />

      {showManager && (
        <CategoryManager
          categories={categories}
          onClose={() => setShowManager(false)}
          onUpdate={handleUpdateCategory}
          onDelete={handleDeleteCategory}
          onCreate={handleAddCategory}
          salary={salary}
          onUpdateSalary={handleUpdateSalary}
        />
      )}

      {showRecurringManager && (
        <RecurringBillsManager
          bills={recurringBills}
          categories={categories}
          onClose={() => setShowRecurringManager(false)}
          onCreate={handleCreateRecurringBill}
          onUpdate={handleUpdateRecurringBill}
          onDelete={handleDeleteRecurringBill}
        />
      )}
    </>
  )
}

export default App
