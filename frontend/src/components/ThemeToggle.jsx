import { useState } from 'react';
import { getTheme, toggleTheme } from '../lib/theme';

export default function ThemeToggle({ className = '' }) {
  const [theme, setTheme] = useState(getTheme());
  const onClick = () => setTheme(toggleTheme());
  const isDark = theme === 'dark';
  return (
    <button
      type="button"
      className={`theme-toggle ${className}`}
      onClick={onClick}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label="Toggle theme"
    >
      {isDark ? '☀' : '☾'}
    </button>
  );
}
