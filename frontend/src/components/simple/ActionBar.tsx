/*
 * "Actions below the light table, plain text buttons not gradient pills:
 * Save, Compare, Open in Studio, Export" (UI_DESIGN.md section 7).
 */

import { useT } from "../../lib/i18n";
import { Button } from "../common/Button";
import styles from "./ActionBar.module.css";

export function ActionBar({
  onSave,
  onExport,
  onCompare,
  onOpenInStudio,
  onReset,
}: {
  onSave: () => void;
  onExport: () => void;
  onCompare: () => void;
  onOpenInStudio: () => void;
  onReset: () => void;
}) {
  const t = useT();
  return (
    <div className={styles.bar}>
      <Button variant="secondary" icon="save" onClick={onSave}>
        {t("simple.action.save")}
      </Button>
      <Button variant="ghost" icon="compare" onClick={onCompare}>
        {t("simple.action.compare")}
      </Button>
      <Button variant="ghost" icon="flow" onClick={onOpenInStudio}>
        {t("simple.action.openInStudio")}
      </Button>
      <Button variant="secondary" icon="export" onClick={onExport}>
        {t("simple.action.export")}
      </Button>
      <Button variant="ghost" onClick={onReset}>
        {t("simple.action.reset")}
      </Button>
    </div>
  );
}
