import { Moon, Sun } from 'lucide-react'

export default function ThemeToggle({ theme, onToggle }) {
  return (
    <button
      className="icon-btn"
      onClick={onToggle}
      aria-label="Toggle theme"
    >
      {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  )
}
