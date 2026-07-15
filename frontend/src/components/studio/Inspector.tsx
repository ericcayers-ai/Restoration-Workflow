/*
 * "Right rail — Inspector. Contextual parameter form for the selected node,
 * generated from that node's param_schema... sliders/selects/toggles, never
 * a bare JSON blob." (UI_DESIGN.md section 8) Also where the license
 * acknowledgement gate and weight download live. InstructIR gets Master
 * Restorer prompt-preset + custom instruction affordances; highlight rescue
 * params surface when present on the schema.
 */

import { useEffect, useState } from "react";
import { listInstructirPrompts, type InstructirPromptPreset } from "../../lib/api";
import { downloadSizeBytes, formatBytes, licenseAbbrev, licenseBadgeHint } from "../../lib/format";
import { useT } from "../../lib/i18n";
import type { DescribedNode, JsonSchemaProperty } from "../../lib/types";
import type { useWeightDownloads } from "../../lib/useWeightDownloads";
import type { Stage } from "../../lib/pipelineStages";
import { Button } from "../common/Button";
import { DownloadRow } from "../common/DownloadRow";
import { Icon } from "../common/Icon";
import styles from "./Inspector.module.css";

function ParamField({
  name,
  spec,
  value,
  onChange,
  titleOverride,
  descriptionOverride,
}: {
  name: string;
  spec: JsonSchemaProperty;
  value: unknown;
  onChange: (value: unknown) => void;
  titleOverride?: string;
  descriptionOverride?: string;
}) {
  const t = useT();
  const types = Array.isArray(spec.type) ? spec.type : [spec.type];
  const nullable = types.includes(null);
  const baseType = types.find((tp) => tp !== null);
  const label = titleOverride ?? spec.title ?? name;
  const description = descriptionOverride ?? spec.description;

  if (baseType === "boolean") {
    return (
      <label className={styles.field}>
        <span>{label}</span>
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          aria-describedby={description ? `${name}-hint` : undefined}
        />
        {description && (
          <span id={`${name}-hint`} className={styles.fieldDescription}>
            {description}
          </span>
        )}
      </label>
    );
  }

  if (spec.enum) {
    const isNumeric = baseType === "integer" || baseType === "number";
    return (
      <label className={styles.field}>
        <span>{label}</span>
        <select
          value={String(value)}
          onChange={(e) => onChange(isNumeric ? Number(e.target.value) : e.target.value)}
        >
          {spec.enum.map((option) => (
            <option key={String(option)} value={String(option)}>
              {String(option)}
            </option>
          ))}
        </select>
        {description && <span className={styles.fieldDescription}>{description}</span>}
      </label>
    );
  }

  if (baseType === "integer" || baseType === "number") {
    const isNull = value === null || value === undefined;
    const parse = (raw: string) => (baseType === "integer" ? parseInt(raw, 10) : parseFloat(raw));
    const hasRange = spec.minimum !== undefined && spec.maximum !== undefined;

    return (
      <div className={styles.field}>
        <div className={styles.fieldHeader}>
          <span>{label}</span>
          {nullable && (
            <label className={styles.autoToggle}>
              <input
                type="checkbox"
                checked={isNull}
                onChange={(e) => onChange(e.target.checked ? null : (spec.minimum ?? 0))}
              />
              {t("studio.inspector.auto")}
            </label>
          )}
        </div>
        {!isNull &&
          (hasRange ? (
            <div className={styles.sliderRow}>
              <input
                type="range"
                min={spec.minimum}
                max={spec.maximum}
                step={baseType === "integer" ? 1 : 0.01}
                value={Number(value)}
                onChange={(e) => onChange(parse(e.target.value))}
                aria-label={label}
              />
              <span className="mono">{String(value)}</span>
            </div>
          ) : (
            <input
              type="number"
              min={spec.minimum}
              max={spec.maximum}
              value={Number(value)}
              onChange={(e) => onChange(parse(e.target.value || "0"))}
              aria-label={label}
            />
          ))}
        {description && <span className={styles.fieldDescription}>{description}</span>}
      </div>
    );
  }

  // Multiline for long instruction strings.
  if (name === "instruction" || (typeof value === "string" && String(value).length > 60)) {
    return (
      <label className={styles.field}>
        <span>{label}</span>
        <textarea
          rows={4}
          value={value != null ? String(value) : ""}
          onChange={(e) => onChange(e.target.value)}
        />
        {description && <span className={styles.fieldDescription}>{description}</span>}
      </label>
    );
  }

  return (
    <label className={styles.field}>
      <span>{label}</span>
      <input
        type="text"
        value={value != null ? String(value) : ""}
        onChange={(e) => onChange(e.target.value)}
      />
      {description && <span className={styles.fieldDescription}>{description}</span>}
    </label>
  );
}

export function Inspector({
  selectedStage,
  described,
  onParamsChange,
  onPinnedChange,
  downloads,
  onAcknowledge,
  onWeightsChanged,
  onBuildEnsemble,
}: {
  selectedStage: Stage | null;
  described: DescribedNode | null;
  onParamsChange: (stageId: string, params: Record<string, unknown>) => void;
  onPinnedChange: (stageId: string, pinned: boolean) => void;
  downloads: ReturnType<typeof useWeightDownloads>;
  onAcknowledge: (nodeId: string) => void;
  onWeightsChanged: () => void;
  onBuildEnsemble?: (params: Record<string, unknown>) => void;
}) {
  const t = useT();
  const [promptLibrary, setPromptLibrary] = useState<InstructirPromptPreset[]>([]);
  const [ensemblePending, setEnsemblePending] = useState(false);

  useEffect(() => {
    if (described?.id !== "instructir") return;
    listInstructirPrompts()
      .then((res) => setPromptLibrary(res.presets))
      .catch(() => setPromptLibrary([]));
  }, [described?.id]);

  if (!selectedStage || !described) {
    return (
      <aside className={styles.inspector} aria-label={t("studio.inspector.title")}>
        <p className={styles.empty}>{t("studio.inspector.empty")}</p>
      </aside>
    );
  }

  const download = downloads.tracker[described.id];
  const needsAck = described.license.requires_acknowledgement && !described.weights.acknowledged;
  const needsDownload = !described.weights.installed;
  const isMaster = described.id === "instructir";
  const isDdcolor = described.id === "ddcolor";
  const size = downloadSizeBytes(described.weights);

  function applyPreset(presetId: string) {
    const preset = promptLibrary.find((p) => p.id === presetId);
    const next: Record<string, unknown> = {
      ...selectedStage!.params,
      prompt_preset: presetId,
    };
    if (preset) {
      next.instruction = preset.instruction;
    }
    onParamsChange(selectedStage!.id, next);
  }

  function paramOverrides(name: string): { title?: string; description?: string } {
    if (name === "mask_highlights") {
      return {
        title: t("studio.inspector.highlightMask"),
        description: t("studio.inspector.highlightMaskHint"),
      };
    }
    if (name === "clip_threshold") {
      return {
        title: t("studio.inspector.clipThreshold"),
        description: t("studio.inspector.highlightMaskHint"),
      };
    }
    return {};
  }

  return (
    <aside className={styles.inspector} aria-label={t("studio.inspector.title")}>
      <header className={styles.header}>
        <h2>{described.display_name}</h2>
        <p className={styles.category}>
          {t(`studio.rail.category.${described.category}`)}
          {isMaster ? ` · ${t("studio.inspector.masterRestorer")}` : ""}
        </p>
      </header>

      {isMaster && (
        <p className={styles.masterHint}>{t("studio.inspector.masterRestorerHint")}</p>
      )}
      {isDdcolor && <p className={styles.masterHint}>{t("studio.inspector.ddcolorHint")}</p>}

      <section className={styles.licenseSection}>
        <span>{t("studio.inspector.license")}</span>
        <span
          className="mono"
          title={
            described.license.requires_acknowledgement
              ? licenseBadgeHint(described.license.kind)
              : undefined
          }
        >
          {described.license.spdx_id}
          {described.license.requires_acknowledgement
            ? ` (${licenseAbbrev(described.license.kind)})`
            : ""}
        </span>
      </section>

      {needsAck && (
        <section className={styles.gate}>
          <p>
            {t("studio.inspector.licenseGate.title", {
              kind: described.license.kind.replace("_", "-"),
            })}
          </p>
          <p className={styles.gateBody}>{t("studio.inspector.licenseGate.body")}</p>
          <Button variant="danger" onClick={() => onAcknowledge(described.id)}>
            {t("studio.inspector.licenseGate.accept")}
          </Button>
        </section>
      )}

      {!needsAck && needsDownload && described.weight_manifest.length > 0 && (
        <section>
          {download && download.state === "running" ? (
            <DownloadRow
              nodeId={described.id}
              displayName={described.display_name}
              download={download}
              onCancel={() => void downloads.cancel(described.id)}
            />
          ) : (
            <Button
              variant="secondary"
              icon="tray"
              onClick={() => {
                void downloads.download(described.id).then(onWeightsChanged);
              }}
            >
              {t("studio.inspector.download", { size: formatBytes(size) })}
            </Button>
          )}
          {download?.state === "error" && (
            <p className={styles.gateBody}>{download.error}</p>
          )}
        </section>
      )}

      {!needsAck && !needsDownload && described.weight_manifest.length > 0 && (
        <p className={styles.installed}>
          <Icon name="check" size={12} />
          {t("studio.inspector.installed")}
        </p>
      )}

      {isMaster && promptLibrary.length > 0 && (
        <label className={styles.field}>
          <span>{t("studio.inspector.promptPreset")}</span>
          <select
            value={String(selectedStage.params.prompt_preset ?? "instruct_only_general")}
            onChange={(e) => applyPreset(e.target.value)}
          >
            {promptLibrary.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.title}
              </option>
            ))}
            <option value="custom">{t("studio.inspector.customInstruction")}</option>
          </select>
          <span className={styles.fieldDescription}>{t("studio.inspector.promptPresetHint")}</span>
        </label>
      )}

      <form className={styles.form} onSubmit={(e) => e.preventDefault()}>
        {Object.entries(described.param_schema.properties)
          .filter(([name]) => !(isMaster && name === "prompt_preset" && promptLibrary.length > 0))
          .map(([name, spec]) => {
            const overrides = paramOverrides(name);
            return (
              <ParamField
                key={name}
                name={name}
                spec={spec}
                value={selectedStage.params[name] ?? spec.default}
                titleOverride={overrides.title}
                descriptionOverride={overrides.description}
                onChange={(value) => {
                  const next = { ...selectedStage.params, [name]: value };
                  if (isMaster && name === "instruction") {
                    next.prompt_preset = "custom";
                  }
                  onParamsChange(selectedStage.id, next);
                }}
              />
            );
          })}

        {isMaster && onBuildEnsemble && !ensemblePending && (
          <Button variant="secondary" onClick={() => setEnsemblePending(true)}>
            {t("studio.ensemble.build")}
          </Button>
        )}

        {isMaster && onBuildEnsemble && ensemblePending && (
          <div className={styles.gate} role="alertdialog" aria-labelledby="ensemble-confirm-title">
            <p id="ensemble-confirm-title">{t("studio.ensemble.confirmTitle")}</p>
            <p className={styles.gateBody}>
              {t("studio.ensemble.confirmBody", {
                preview: String(selectedStage.params.prompt_preset ?? "custom"),
              })}
            </p>
            <div className={styles.confirmRow}>
              <Button
                variant="primary"
                onClick={() => {
                  setEnsemblePending(false);
                  onBuildEnsemble(selectedStage.params);
                }}
              >
                {t("studio.ensemble.confirm")}
              </Button>
              <Button variant="ghost" onClick={() => setEnsemblePending(false)}>
                {t("studio.ensemble.cancel")}
              </Button>
            </div>
          </div>
        )}

        {described.weight_manifest.length > 0 && (
          <label className={styles.pinnedRow}>
            <input
              type="checkbox"
              checked={selectedStage.pinned}
              onChange={(e) => onPinnedChange(selectedStage.id, e.target.checked)}
            />
            <span>{t("studio.inspector.keepLoaded")}</span>
          </label>
        )}
      </form>
    </aside>
  );
}
