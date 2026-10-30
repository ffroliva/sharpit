/** `system` follows `prefers-color-scheme`; `light`/`dark` pin it via `data-theme` on <html> (DESIGN.md). */
export type Theme = 'system' | 'light' | 'dark';

const KEY = 'sharpit.theme';
const ORDER: Theme[] = ['system', 'light', 'dark'];

export function loadTheme(): Theme {
  let saved: string | null = null;
  try {
    saved = localStorage.getItem(KEY);
  } catch {
    // storage blocked: fall back to the system theme
  }
  return ORDER.includes(saved as Theme) ? (saved as Theme) : 'system';
}

export function applyTheme(theme: Theme): void {
  if (theme === 'system') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // not persisted; the choice still holds for this page
  }
}

export const nextTheme = (theme: Theme): Theme => ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length]!;
