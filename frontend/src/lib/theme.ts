// Appearance preference. "system" follows the operating system; a stored choice is a per-browser convenience.
export type Theme = 'system' | 'light' | 'dark'
const KEY = 'depositflow-theme'

export function storedTheme(): Theme {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

export function applyTheme(theme: Theme) {
  if (theme === 'system') delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = theme
  try {
    if (theme === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, theme)
  } catch {
    // Storage can be unavailable (private windows); the choice still applies for this visit.
  }
}
