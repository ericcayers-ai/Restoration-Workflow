/*
 * "A single full-bleed drop target, centered, minimal chrome"
 * (UI_DESIGN.md section 7). Keyboard-operable per section 6: focusable,
 * Enter/Space opens the file picker, exactly like a click would.
 */

import { useCallback, useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import { Icon } from "../common/Icon";
import styles from "./DropZone.module.css";

const ACCEPTED = ".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff";

export function DropZone({ onFile }: { onFile: (file: File) => void }) {
  const t = useT();
  const [active, setActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const openPicker = useCallback(() => inputRef.current?.click(), []);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (file) onFile(file);
    },
    [onFile],
  );

  return (
    <div
      className={styles.zone}
      data-active={active}
      role="button"
      tabIndex={0}
      aria-label={t("simple.dropzone.ariaLabel")}
      onClick={openPicker}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openPicker();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setActive(true);
      }}
      onDragLeave={() => setActive(false)}
      onDrop={(e) => {
        e.preventDefault();
        setActive(false);
        handleFiles(e.dataTransfer.files);
      }}
    >
      <div className={styles.iconWrap}>
        <Icon name="upload" size={40} />
      </div>
      <p className={styles.title}>{t("simple.dropTitle")}</p>
      <p className={styles.subtitle}>{t("simple.dropSubtitle")}</p>
      <p className={styles.hint}>{t("simple.dropHint")}</p>
      <input
        ref={inputRef}
        className={styles.input}
        type="file"
        accept={ACCEPTED}
        tabIndex={-1}
        aria-hidden="true"
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
