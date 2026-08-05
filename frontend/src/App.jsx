import { useState, useEffect, useCallback } from 'react'
import { Settings, Mail, Check, Landmark, Inbox } from 'lucide-react'
import MonthPicker from './components/MonthPicker'
import ExpensePieChart from './components/ExpensePieChart'
import ExpenseList from './components/ExpenseList'
import CategoryManager from './components/CategoryManager'
import BankConnectModal from './components/BankConnectModal'
import ImportActivityModal from './components/ImportActivityModal'
import ThemeToggle from './components/ThemeToggle'
import {
  getCategories,
  createCategory,
  updateCategory,
  deleteCategory,
  getExpenses,
  updateExpense,
  deleteExpense,
  getSummary,
  sendInsightsEmail,
  getSalary,
  updateSalary,
  clearSalary,
  getBankConnections,
  connectBank,
  submitScraperOtp,
  deleteBankConnection,
  reverifyBankConnection,
  submitReverifyOtp,
  syncBank,
  getBankTransactions,
  restoreBankTransaction,
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
  const [sendingEmail, setSendingEmail] = useState(false)
  const [emailFeedback, setEmailFeedback] = useState(null)
  const [salary, setSalary] = useState(null)
  const [bankConnections, setBankConnections] = useState([])
  const [showBankManager, setShowBankManager] = useState(false)
  const [activityTxns, setActivityTxns] = useState([])
  const [showImportActivity, setShowImportActivity] = useState(false)

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

  const loadBankConnections = useCallback(() => {
    return getBankConnections()
      .then(setBankConnections)
      .catch(() => {})
  }, [])

  const loadActivity = useCallback(() => {
    return getBankTransactions(undefined, month)
      .then(setActivityTxns)
      .catch(() => {})
  }, [month])

  useEffect(() => {
    loadBankConnections()
  }, [loadBankConnections])

  useEffect(() => {
    loadActivity()
  }, [loadActivity])

  async function handleDeleteExpense(id) {
    await deleteExpense(id)
    setExpenses((prev) => prev.filter((e) => e.id !== id))
    const sum = await getSummary(month)
    setSummary(sum)
    await loadActivity()
  }

  async function handleRecategorizeExpense(id, categoryId) {
    const updated = await updateExpense(id, { category_id: categoryId, remember: true })
    setExpenses((prev) => prev.map((e) => (e.id === id ? updated : e)))
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

  async function handleUpdateSalary(amount) {
    const updated = await updateSalary(month, amount)
    setSalary(updated)
  }

  async function handleConnectBank(payload) {
    const result = await connectBank(payload)
    if (result.status === 'otp_required') return result
    setBankConnections((prev) => [...prev, result])
    return result
  }

  async function handleSubmitScraperOtp(sessionId, otpCode, label) {
    const result = await submitScraperOtp(sessionId, otpCode, label)
    if (result.status === 'otp_required') return result
    setBankConnections((prev) => [...prev, result])
    return result
  }

  async function handleDeleteBankConnection(id) {
    await deleteBankConnection(id)
    setBankConnections((prev) => prev.filter((c) => c.id !== id))
  }

  async function handleReverifyBank(id) {
    const result = await reverifyBankConnection(id)
    if (result.status === 'otp_required') return result
    setBankConnections((prev) => prev.map((c) => (c.id === id ? result : c)))
    return result
  }

  async function handleSubmitReverifyOtp(id, sessionId, otpCode) {
    const result = await submitReverifyOtp(id, sessionId, otpCode)
    if (result.status === 'otp_required') return result
    setBankConnections((prev) => prev.map((c) => (c.id === id ? result : c)))
    return result
  }

  async function handleSyncBank(connectionId, month) {
    try {
      await syncBank(connectionId, month)
    } finally {
      // Refetch even on failure — a failed sync (e.g. OTP_REQUIRED) flips the
      // connection's status to 'error' server-side, which is what makes the
      // reconnect button appear. loadMonthData matters because a sync now
      // creates expenses directly, so the list and pie are stale without it.
      await Promise.all([loadBankConnections(), loadActivity(), loadMonthData()])
      setSalary(await getSalary(month))
    }
  }

  async function handleRestoreBankTxn(id) {
    await restoreBankTransaction(id)
    await Promise.all([loadActivity(), loadMonthData()])
  }

  async function handleClearSalary() {
    await clearSalary(month)
    setSalary(await getSalary(month))
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

  // With nothing left to approve, the only thing wanting attention is spending
  // the categorizer couldn't place.
  const uncategorizedCount = expenses.filter((e) => e.category_name === 'Uncategorized').length

  return (
    <>
      <header className="app-header">
        <h1 className="app-title">Expenses</h1>
        <div className="header-actions">
          <ThemeToggle theme={theme} onToggle={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))} />
          <button
            className="icon-btn"
            onClick={() => setShowBankManager(true)}
            aria-label="Manage bank connections"
          >
            <Landmark size={18} />
          </button>
          <button
            className={uncategorizedCount ? 'icon-btn header-icon-badge' : 'icon-btn'}
            data-count={uncategorizedCount || undefined}
            onClick={() => setShowImportActivity(true)}
            aria-label="View imported bank activity"
          >
            <Inbox size={18} />
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

      <ExpensePieChart summary={summary} />

      <ExpenseList
        expenses={expenses}
        categories={categories}
        onDelete={handleDeleteExpense}
        onRecategorize={handleRecategorizeExpense}
      />

      {showManager && (
        <CategoryManager
          categories={categories}
          onClose={() => setShowManager(false)}
          onUpdate={handleUpdateCategory}
          onDelete={handleDeleteCategory}
          onCreate={handleAddCategory}
          salary={salary}
          onUpdateSalary={handleUpdateSalary}
          onClearSalary={handleClearSalary}
        />
      )}

      {showBankManager && (
        <BankConnectModal
          connections={bankConnections}
          onClose={() => setShowBankManager(false)}
          onConnect={handleConnectBank}
          onSubmitOtp={handleSubmitScraperOtp}
          onDelete={handleDeleteBankConnection}
          onSync={handleSyncBank}
          onReverify={handleReverifyBank}
          onSubmitReverifyOtp={handleSubmitReverifyOtp}
          month={month}
        />
      )}

      {showImportActivity && (
        <ImportActivityModal
          transactions={activityTxns}
          onClose={() => setShowImportActivity(false)}
          onRestore={handleRestoreBankTxn}
        />
      )}
    </>
  )
}

export default App
