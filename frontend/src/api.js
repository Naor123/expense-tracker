import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
})

export const getCategories = () => api.get('/categories').then((r) => r.data)
export const createCategory = (name, color) =>
  api.post('/categories', { name, color }).then((r) => r.data)
export const updateCategory = (id, data) =>
  api.put(`/categories/${id}`, data).then((r) => r.data)
export const deleteCategory = (id) => api.delete(`/categories/${id}`)

export const getExpenses = (month) =>
  api.get('/expenses', { params: { month } }).then((r) => r.data)
export const createExpense = (expense) =>
  api.post('/expenses', expense).then((r) => r.data)
export const deleteExpense = (id) => api.delete(`/expenses/${id}`)

export const getSummary = (month) =>
  api.get('/summary', { params: { month } }).then((r) => r.data)

export const getMonths = () => api.get('/months').then((r) => r.data)

export const sendInsightsEmail = (month) =>
  api.post('/insights/send-email', null, { params: { month } }).then((r) => r.data)

export const getSalary = (month) =>
  api.get('/salary', { params: { month } }).then((r) => r.data)
export const updateSalary = (month, amount) =>
  api.put('/salary', { amount }, { params: { month } }).then((r) => r.data)

export const getBankConnections = () => api.get('/bank/connections').then((r) => r.data)
export const connectBank = (payload) => api.post('/bank/connect', payload).then((r) => r.data)
export const submitScraperOtp = (sessionId, otpCode, label) =>
  api
    .post('/bank/connect/otp', { session_id: sessionId, otp_code: otpCode, label })
    .then((r) => r.data)
export const deleteBankConnection = (id) => api.delete(`/bank/connections/${id}`)
export const reverifyBankConnection = (id) =>
  api.post(`/bank/connections/${id}/reverify`).then((r) => r.data)
export const submitReverifyOtp = (id, sessionId, otpCode) =>
  api
    .post(`/bank/connections/${id}/reverify/otp`, { session_id: sessionId, otp_code: otpCode })
    .then((r) => r.data)
export const syncBank = (connectionId, dateFrom, dateTo) =>
  api
    .post('/bank/sync', null, { params: { connection_id: connectionId, date_from: dateFrom, date_to: dateTo } })
    .then((r) => r.data)

export const getBankTransactions = (status) =>
  api.get('/bank/transactions', { params: { status } }).then((r) => r.data)
export const approveBankTransaction = (id, data) =>
  api.post(`/bank/transactions/${id}/approve`, data).then((r) => r.data)
export const ignoreBankTransaction = (id) =>
  api.post(`/bank/transactions/${id}/ignore`).then((r) => r.data)
export const markBankTransactionSalary = (id, saveRule) =>
  api.post(`/bank/transactions/${id}/mark-salary`, { save_rule: saveRule }).then((r) => r.data)
export const approveBankTransactionsBulk = (ids) =>
  api.post('/bank/transactions/approve-bulk', { ids }).then((r) => r.data)

export const getCategoryRules = () => api.get('/category-rules').then((r) => r.data)
export const createCategoryRule = (pattern, categoryId) =>
  api.post('/category-rules', { pattern, category_id: categoryId }).then((r) => r.data)
export const deleteCategoryRule = (id) => api.delete(`/category-rules/${id}`)

export default api
