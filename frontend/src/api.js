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

export const getRecurringBills = () => api.get('/recurring-bills').then((r) => r.data)
export const createRecurringBill = (data) =>
  api.post('/recurring-bills', data).then((r) => r.data)
export const updateRecurringBill = (id, data) =>
  api.put(`/recurring-bills/${id}`, data).then((r) => r.data)
export const deleteRecurringBill = (id) => api.delete(`/recurring-bills/${id}`)

export const sendInsightsEmail = (month) =>
  api.post('/insights/send-email', null, { params: { month } }).then((r) => r.data)

export const getSalary = (month) =>
  api.get('/salary', { params: { month } }).then((r) => r.data)
export const updateSalary = (month, amount) =>
  api.put('/salary', { amount }, { params: { month } }).then((r) => r.data)

export default api
