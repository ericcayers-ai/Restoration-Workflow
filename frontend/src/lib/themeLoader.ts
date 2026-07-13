/*
 * Loadable theme files (ARCHITECTURE.md section 7, UI_DESIGN.md section 9).
 * A theme file is JSON mapping design-token names to CSS custom-property values.
 */

export interface ThemeFile {
  id: string;
  label: string;
  tokens: Record<string, string>;
}

const TOKEN_PREFIX = "--";

export async function listThemeFiles(): Promise<ThemeFile[]> {
  const index = await fetch("/themes/index.json").then((r) => (r.ok ? r.json() : []));
  return Array.isArray(index) ? index : [];
}

export function applyThemeFile(theme: ThemeFile): void {
  const root = document.documentElement;
  for (const [key, value] of Object.entries(theme.tokens)) {
    const prop = key.startsWith(TOKEN_PREFIX) ? key : `${TOKEN_PREFIX}${key}`;
    root.style.setProperty(prop, value);
  }
  root.dataset.theme = theme.id;
}

export function clearThemeFileOverrides(): void {
  const root = document.documentElement;
  for (const name of Array.from(root.style)) {
    if (name.startsWith(TOKEN_PREFIX)) root.style.removeProperty(name);
  }
}
