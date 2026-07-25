/*
 * Save/load pipelines as named presets. Phase 4: dynamic suggestions from
 * /api/auto/suggest; user-saved presets in the load dropdown (builtins filtered).
 */

import { useEffect, useRef, useState } from "react";
import { listPresets } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { PipelineJson, Preset, SuggestedPreset } from "../../lib/types";
import { Button } from "../common/Button";
import styles from "./PresetBar.module.css";

export function PresetBar({
  onSave,
  onLoad,
  onImport,
  onExport,
  onLoadSuggestion,
  refreshToken,
  suggestions = [],
}: {
  onSave: (name: string) => void;
  onLoad: (name: string) => void;
  onImport: (file: File) => void;
  onExport: () => void;
  onLoadSuggestion?: (pipeline: PipelineJson, name: string) => void;
  refreshToken: number;
  suggestions?: SuggestedPreset[];
}) {
  const t = useT();
  const [presets, setPresets] = useState<Preset[]>([]);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const importRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listPresets()
      .then((all) => setPresets(all.filter((p) => !p.builtin)))
      .catch(() => setPresets([]));
  }, [refreshToken]);

  function commitSave() {
    const trimmed = name.trim();
    if (!trimmed) return;
    onSave(trimmed);
    setSaving(false);
    setName("");
  }

  return (
    <div className={styles.bar}>
      {saving ? (
        <div className={styles.saveGroup}>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("studio.presets.namePrompt")}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitSave();
              if (e.key === "Escape") setSaving(false);
            }}
          />
          <Button variant="primary" size="small" onClick={commitSave}>
            {t("common.save")}
          </Button>
          <Button variant="ghost" size="small" onClick={() => setSaving(false)}>
            {t("common.cancel")}
          </Button>
        </div>
      ) : (
        <Button variant="ghost" size="small" icon="save" onClick={() => setSaving(true)}>
          {t("studio.presets.save")}
        </Button>
      )}

      <select
        className={styles.select}
        value=""
        onChange={(e) => {
          if (e.target.value) onLoad(e.target.value);
        }}
        aria-label={t("studio.presets.load")}
      >
        <option value="">{t("studio.presets.user")}</option>
        {presets.map((preset) => (
          <option key={preset.name} value={preset.name}>
            {preset.name}
          </option>
        ))}
      </select>

      {suggestions.length > 0 && onLoadSuggestion && (
        <div className={styles.suggestions} role="group" aria-label={t("studio.presets.suggested")}>
          <span className={styles.suggestLabel}>{t("studio.presets.suggested")}</span>
          {suggestions.map((s) => (
            <Button
              key={`${s.goal}-${s.name}`}
              variant="ghost"
              size="small"
              title={s.description}
              onClick={() => onLoadSuggestion(s.pipeline, s.name)}
            >
              {s.name}
            </Button>
          ))}
        </div>
      )}

      <Button variant="ghost" size="small" icon="upload" onClick={() => importRef.current?.click()}>
        {t("studio.presets.import")}
      </Button>
      <input
        ref={importRef}
        type="file"
        accept=".txt"
        className="visually-hidden"
        aria-label={t("studio.presets.import")}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onImport(file);
          e.target.value = "";
        }}
      />

      <div className={styles.spacer} />

      <Button variant="ghost" size="small" icon="export" onClick={onExport}>
        {t("studio.presets.export")}
      </Button>
    </div>
  );
}
