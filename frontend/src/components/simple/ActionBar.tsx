/*
 * "Actions below the light table, plain text buttons not gradient pills:
 * Save, Open in Studio, Export" (UI_DESIGN.md section 7). Compare lives in
 * LightTable's view-mode control — no competing Compare button here.
 *
 * Hierarchy: one primary (Save), one secondary (Export), the rest ghost —
 * so the next step is obvious instead of five equal-weight choices.
 */

import { useT } from "../../lib/i18n";
import { Button } from "../common/Button";
import styles from "./ActionBar.module.css";

export function ActionBar({
  onSave,
  onExport,
  onOpenInStudio,
  onReset,
  onTryAgain,
}: {
  onSave: () => void;
  onExport: () => void;
  onOpenInStudio?: () => void;
  onReset: () => void;
  onTryAgain?: () => void;
}) {
  const t = useT();
  return (
    <div className={styles.bar} role="toolbar" aria-label={t("simple.after")}>
      <div className={styles.primaryGroup}>
        <Button variant="primary" icon="save" onClick={onSave}>
          {t("simple.action.save")}
        </Button>
        <Button variant="secondary" icon="export" onClick={onExport}>
          {t("simple.action.export")}
        </Button>
      </div>
      <span className={styles.divider} aria-hidden />
      <div className={styles.secondaryGroup}>
        {onOpenInStudio && (
          <Button variant="ghost" icon="flow" onClick={onOpenInStudio}>
            {t("simple.action.openInStudio")}
          </Button>
        )}
        <Button variant="ghost" onClick={onTryAgain ?? onReset}>
          {t("simple.action.tryAgain")}
        </Button>
        <Button variant="ghost" onClick={onReset}>
          {t("simple.action.newPhoto")}
        </Button>
      </div>
    </div>
  );
}
