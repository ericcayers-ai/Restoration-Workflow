/*
 * "Actions below the light table, plain text buttons not gradient pills:
 * Save, Open in Studio, Export" (UI_DESIGN.md section 7). Compare lives in
 * LightTable's view-mode control — no competing Compare button here.
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
      <Button variant="secondary" icon="save" onClick={onSave}>
        {t("simple.action.save")}
      </Button>
      {onOpenInStudio && (
        <Button variant="ghost" icon="flow" onClick={onOpenInStudio}>
          {t("simple.action.openInStudio")}
        </Button>
      )}
      <Button variant="secondary" icon="export" onClick={onExport}>
        {t("simple.action.export")}
      </Button>
      <Button variant="ghost" onClick={onTryAgain ?? onReset}>
        {t("simple.action.tryAgain")}
      </Button>
      <Button variant="ghost" onClick={onReset}>
        {t("simple.action.newPhoto")}
      </Button>
    </div>
  );
}
