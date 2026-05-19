// Tiny theme manager. Reads / writes localStorage, applies a data attribute on <html>.

const KEY = 'et_theme';

export function getTheme() {
  return (typeof window !== 'undefined' && localStorage.getItem(KEY)) || 'dark';
}

export function applyTheme(theme) {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-theme', theme);
}

export function setTheme(theme) {
  localStorage.setItem(KEY, theme);
  applyTheme(theme);
}

export function toggleTheme() {
  const next = getTheme() === 'dark' ? 'light' : 'dark';
  setTheme(next);
  return next;
}
