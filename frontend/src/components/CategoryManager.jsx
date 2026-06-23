import { useState } from 'react'
import { X, Save, Trash2, Plus, Pencil, Check } from 'lucide-react'

export default function CategoryManager({
  categories,
  onClose,
  onUpdate,
  onDelete,
  onCreate,
  salary,
  onUpdateSalary,
}) {
  const [edits, setEdits] = useState({})
  const [errors, setErrors] = useState({})
  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState('#4f46e5')
  const [createError, setCreateError] = useState('')
  const [editingSalary, setEditingSalary] = useState(false)
  const [salaryAmount, setSalaryAmount] = useState('')
  const [salarySubmitting, setSalarySubmitting] = useState(false)
  const [salaryError, setSalaryError] = useState('')

  function startEditSalary() {
    setSalaryAmount(salary?.amount != null ? String(salary.amount) : '')
    setEditingSalary(true)
    setSalaryError('')
  }

  async function handleSaveSalary() {
    if (!salaryAmount || Number(salaryAmount) <= 0) return
    setSalarySubmitting(true)
    setSalaryError('')
    try {
      await onUpdateSalary(Number(salaryAmount))
      setEditingSalary(false)
    } catch {
      setSalaryError('Could not save salary.')
    } finally {
      setSalarySubmitting(false)
    }
  }

  function getEdit(cat) {
    return edits[cat.id] ?? { name: cat.name, color: cat.color }
  }

  function setEdit(id, field, value) {
    setEdits((prev) => ({
      ...prev,
      [id]: { ...(prev[id] ?? categories.find((c) => c.id === id)), [field]: value },
    }))
  }

  async function handleSave(cat) {
    const edit = getEdit(cat)
    setErrors((prev) => ({ ...prev, [cat.id]: '' }))
    try {
      await onUpdate(cat.id, { name: edit.name, color: edit.color })
    } catch (err) {
      setErrors((prev) => ({
        ...prev,
        [cat.id]: err.response?.status === 409 ? 'That name is already used.' : 'Could not update category.',
      }))
    }
  }

  async function handleDelete(cat) {
    setErrors((prev) => ({ ...prev, [cat.id]: '' }))
    try {
      await onDelete(cat.id)
    } catch (err) {
      setErrors((prev) => ({
        ...prev,
        [cat.id]: err.response?.status === 409
          ? 'This category still has expenses. Remove them first.'
          : 'Could not delete category.',
      }))
    }
  }

  async function handleCreate() {
    if (!newName.trim()) return
    try {
      await onCreate(newName.trim(), newColor)
      setNewName('')
      setNewColor('#4f46e5')
      setCreateError('')
    } catch (err) {
      setCreateError(err.response?.status === 409 ? 'Category name already exists.' : 'Could not create category.')
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Settings</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <h3 className="card-title">Net Salary</h3>
        {!editingSalary ? (
          <div className="salary-row">
            <span className="salary-amount">
              {salary?.amount != null ? `₪${salary.amount.toFixed(2)}` : 'Not set'}
            </span>
            <button className="icon-btn" onClick={startEditSalary} aria-label="Edit net salary">
              <Pencil size={16} />
            </button>
          </div>
        ) : (
          <div className="salary-edit">
            <input
              type="number"
              min="0.01"
              step="0.01"
              inputMode="decimal"
              placeholder="0.00"
              value={salaryAmount}
              onChange={(e) => setSalaryAmount(e.target.value)}
              autoFocus
            />
            <button className="inline-btn primary" onClick={handleSaveSalary} disabled={salarySubmitting}>
              <Check size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
              Save
            </button>
            <button className="inline-btn" onClick={() => setEditingSalary(false)}>
              Cancel
            </button>
          </div>
        )}
        {salaryError && <p className="category-manager-error">{salaryError}</p>}

        <h3 className="card-title">Categories</h3>
        <div className="category-manager-list">
          {categories.map((cat) => {
            const edit = getEdit(cat)
            return (
              <div key={cat.id}>
                <div className="category-manager-row">
                  <input
                    type="color"
                    value={edit.color}
                    onChange={(e) => setEdit(cat.id, 'color', e.target.value)}
                  />
                  <input
                    type="text"
                    value={edit.name}
                    onChange={(e) => setEdit(cat.id, 'name', e.target.value)}
                  />
                  <div className="category-manager-actions">
                    <button className="save" onClick={() => handleSave(cat)} aria-label="Save">
                      <Save size={16} />
                    </button>
                    <button className="delete" onClick={() => handleDelete(cat)} aria-label="Delete">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
                {errors[cat.id] && <p className="category-manager-error">{errors[cat.id]}</p>}
              </div>
            )
          })}
        </div>

        <div className="add-category-footer">
          <div className="add-category-row">
            <input
              type="color"
              value={newColor}
              onChange={(e) => setNewColor(e.target.value)}
            />
            <input
              type="text"
              placeholder="New category name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <button className="icon-btn" onClick={handleCreate} aria-label="Add category">
              <Plus size={18} />
            </button>
          </div>
          {createError && <p className="category-manager-error">{createError}</p>}
        </div>
      </div>
    </div>
  )
}
