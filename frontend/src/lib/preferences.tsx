/*
 * Theme and UI-scale state (UI_DESIGN.md section 6). Both are applied to
 * `document.documentElement` — as a `data-theme` attribute and a `--ui-scale`
 * custom property respectively — by an inline script in index.html *before*
 * this module ever runs, so there is no flash of the wrong theme on load.
 * This context's job is: read what's already applied, then keep it in sync
 * with user changes and persist them.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Theme = "dark" | "light" | "high-contrast";

const THEME_KEY = "restoration:theme";
const SCALE_KEY = "restoration:ui-scale";
export const SCALE_MIN = 0.85;
export const SCALE_MAX = 1.4;
export const SCALE_STEP = 0.1;

function readInitialTheme(): Theme {
  const applied = document.documentElement.dataset.theme;
  return applied === "light" || applied === "high-contrast" ? applied : "dark";
}

function readInitialScale(): number {
  const raw = Number(document.documentElement.style.getPropertyValue("--ui-scale"));
  return Number.isFinite(raw) && raw > 0 ? raw : 1;
}

interface PreferencesValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  scale: number;
  setScale: (scale: number) => void;
}

const PreferencesContext = createContext<PreferencesValue | null>(null);

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readInitialTheme);
  const [scale, setScaleState] = useState<number>(readInitialScale);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      // Private-browsing storage denial must not break theming — the
      // in-memory state above still works for the rest of the session.
    }
  }, [theme]);

  useEffect(() => {
    document.documentElement.style.setProperty("--ui-scale", String(scale));
    try {
      localStorage.setItem(SCALE_KEY, String(scale));
    } catch {
      // See above.
    }
  }, [scale]);

  const setTheme = useCallback((next: Theme) => setThemeState(next), []);
  const setScale = useCallback(
    (next: number) => setScaleState(Math.min(SCALE_MAX, Math.max(SCALE_MIN, next))),
    [],
  );

  const value = useMemo(
    () => ({ theme, setTheme, scale, setScale }),
    [theme, setTheme, scale, setScale],
  );

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): PreferencesValue {
  const ctx = useContext(PreferencesContext);
  if (!ctx) throw new Error("usePreferences must be used within PreferencesProvider");
  return ctx;
}
