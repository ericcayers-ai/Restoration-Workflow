/*
 * Theme (dark/light/high-contrast) and UI-scale controls — both exposed
 * directly in-app, not buried in an OS setting (UI_DESIGN.md section 2, 6).
 */

import { SCALE_MAX, SCALE_MIN, SCALE_STEP, usePreferences, type Theme } from "../../lib/preferences";
import { useT } from "../../lib/i18n";
import { Icon } from "./Icon";
import styles from "./PreferencesBar.module.css";

const THEMES: { value: Theme; icon: "aperture" | "loupe" | "contrast" }[] = [
  { value: "dark", icon: "aperture" },
  { value: "light", icon: "loupe" },
  { value: "high-contrast", icon: "contrast" },
];

export function ThemeToggle() {
  const { theme, setTheme } = usePreferences();
  const t = useT();

  return (
    <div
      className={styles.segmented}
      role="radiogroup"
      aria-label={t("theme.label")}
    >
      {THEMES.map(({ value }) => {
        const label =
          value === "dark"
            ? t("theme.dark")
            : value === "light"
              ? t("theme.light")
              : value === "high-contrast"
                ? t("theme.highContrast")
                : t("theme.custom");
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={theme === value}
            aria-label={label}
            className={`${styles.segment} ${theme === value ? styles.segmentActive : ""}`}
            onClick={() => setTheme(value)}
            title={label}
          >
            {value === "dark" ? "Dk" : value === "light" ? "Lt" : "HC"}
          </button>
        );
      })}
    </div>
  );
}

export function ScaleControl() {
  const { scale, setScale } = usePreferences();
  const t = useT();
  const percent = Math.round(scale * 100);

  return (
    <div className={styles.group} role="group" aria-label={t("scale.label")}>
      <button
        type="button"
        className={styles.iconButton}
        onClick={() => setScale(scale - SCALE_STEP)}
        disabled={scale <= SCALE_MIN}
        aria-label={t("scale.decrease")}
      >
        <Icon name="chevron-down" size={14} style={{ transform: "rotate(90deg)" }} />
      </button>
      <span className={styles.scaleValue} aria-live="polite">
        <span className="visually-hidden">{t("scale.value", { percent })}</span>
        <span aria-hidden>{percent}%</span>
      </span>
      <button
        type="button"
        className={styles.iconButton}
        onClick={() => setScale(scale + SCALE_STEP)}
        disabled={scale >= SCALE_MAX}
        aria-label={t("scale.increase")}
      >
        <Icon name="chevron-down" size={14} style={{ transform: "rotate(-90deg)" }} />
      </button>
    </div>
  );
}
