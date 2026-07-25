/*
 * "A single full-bleed drop target, centered, minimal chrome"
 * (UI_DESIGN.md section 7). Keyboard-operable per section 6: focusable
 * label opens the file picker on Enter/Space, exactly like a click would.
 *
 * Batch folder picking uses a separate webkitdirectory input so the primary
 * click stays a normal photo picker (Studio already separates these).
 */

import { useCallback, useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import { Icon } from "../common/Icon";
import styles from "./DropZone.module.css";

const ACCEPTED = ".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff";

export function DropZone({
  onFile,
  onFiles,
}: {
  onFile: (file: File) => void;
  /** Batch mode: process every image in a dropped folder (ROADMAP.md 4.5.5). */
  onFiles?: (files: File[]) => void;
}) {
  const t = useT();
  const [active, setActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files?.length) return;
      const imageFiles = Array.from(files).filter((f) =>
        /\.(jpe?g|png|webp|bmp|tiff?)$/i.test(f.name),
      );
      if (onFiles && imageFiles.length > 1) {
        onFiles(imageFiles);
        return;
      }
      const file = imageFiles[0] ?? files[0];
      if (file) onFile(file);
    },
    [onFile, onFiles],
  );

  return (
    <label
      className={`${styles.zone} grain-surface`}
      data-active={active}
      aria-label={t("simple.dropzone.ariaLabel")}
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
        <Icon name="upload" size={36} />
      </div>
      <p className={styles.title}>{t("simple.dropTitle")}</p>
      <p className={styles.subtitle}>{t("simple.dropSubtitle")}</p>
      <p className={styles.hint}>{onFiles ? t("simple.dropHintBatch") : t("simple.dropHint")}</p>
      {onFiles && (
        <button
          type="button"
          className={styles.folderButton}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            folderRef.current?.click();
          }}
        >
          {t("simple.dropFolder")}
        </button>
      )}
      <input
        ref={inputRef}
        className={styles.input}
        type="file"
        accept={ACCEPTED}
        multiple={Boolean(onFiles)}
        tabIndex={-1}
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />
      {onFiles && (
        <input
          ref={folderRef}
          className={styles.input}
          type="file"
          accept={ACCEPTED}
          multiple
          // @ts-expect-error webkitdirectory is non-standard but widely supported
          webkitdirectory=""
          tabIndex={-1}
          aria-label={t("simple.dropFolder")}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      )}
    </label>
  );
}
