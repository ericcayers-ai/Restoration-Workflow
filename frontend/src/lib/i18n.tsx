/*
 * The message-catalog seam (UI_DESIGN.md section 6, ROADMAP.md Phase 7).
 * Only English ships at launch, but every UI string is routed through here —
 * retrofitting i18n after strings are scattered through components is far
 * more expensive than reserving this seam now. Adding a locale later is
 * "translate en.json, add it to `catalogs`," not a rewrite.
 */

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import en from "../locales/en.json";

type Catalog = typeof en;
export type MessageKey = keyof Catalog;
type Vars = Record<string, string | number>;

const catalogs: Record<string, Catalog> = { en };

type TranslateFn = (key: MessageKey, vars?: Vars) => string;

const I18nContext = createContext<TranslateFn>((key) => key);

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{\{(\w+)\}\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}

export function I18nProvider({
  locale = "en",
  children,
}: {
  locale?: string;
  children: ReactNode;
}) {
  // "en" is always present in `catalogs` (it's the literal object above), so
  // this fallback can never actually be undefined.
  const catalog = catalogs[locale] ?? catalogs.en!;

  const t = useCallback<TranslateFn>(
    (key, vars) => interpolate(catalog[key] ?? key, vars),
    [catalog],
  );

  const value = useMemo(() => t, [t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useT(): TranslateFn {
  return useContext(I18nContext);
}
