/*
 * "Right rail — Inspector. Contextual parameter form for the selected node,
 * generated from that node's param_schema... sliders/selects/toggles, never
 * a bare JSON blob." (UI_DESIGN.md section 8) Also where the license
 * acknowledgement gate and weight download live for a node reached directly
 * in Studio Mode (ARCHITECTURE.md section 6) — Simple Mode never needs this,
 * since its default pipeline is guaranteed permissive-only.
 */

import { formatBytes, licenseAbbrev } from "../../lib/format";
import { useT } from "../../lib/i18n";
import type { DescribedNode, JsonSchemaProperty } from "../../lib/types";
import type { useWeightDownloads } from "../../lib/useWeightDownloads";
import type { RFNode } from "../../lib/canvasPipeline";
import { Button } from "../common/Button";
import { DownloadRow } from "../common/DownloadRow";
import { Icon } from "../common/Icon";
import styles from "./Inspector.module.css";

function ParamField({
  name,
  spec,
  value,
  onChange,
}: {
  name: string;
  spec: JsonSchemaProperty;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const types = Array.isArray(spec.type) ? spec.type : [spec.type];
  const nullable = types.includes(null);
  const baseType = types.find((tp) => tp !== null);
  const label = spec.title ?? name;

  if (baseType === "boolean") {
    return (
      <label className={styles.field}>
        <span>{label}</span>
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
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
              Auto
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
            />
          ))}
        {spec.description && <span className={styles.fieldDescription}>{spec.description}</span>}
      </div>
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
      {spec.description && <span className={styles.fieldDescription}>{spec.description}</span>}
    </label>
  );
}

export function Inspector({
  selectedNode,
  described,
  onParamsChange,
  onPinnedChange,
  downloads,
  onAcknowledge,
  onWeightsChanged,
}: {
  selectedNode: RFNode | null;
  described: DescribedNode | null;
  onParamsChange: (nodeId: string, params: Record<string, unknown>) => void;
  onPinnedChange: (nodeId: string, pinned: boolean) => void;
  downloads: ReturnType<typeof useWeightDownloads>;
  onAcknowledge: (nodeId: string) => void;
  onWeightsChanged: () => void;
}) {
  const t = useT();

  if (!selectedNode || !described) {
    return (
      <aside className={styles.inspector} aria-label={t("studio.inspector.title")}>
        <p className={styles.empty}>{t("studio.inspector.empty")}</p>
      </aside>
    );
  }

  const download = downloads.tracker[described.id];
  const needsAck = described.license.requires_acknowledgement && !described.weights.acknowledged;
  const needsDownload = !described.weights.installed;

  return (
    <aside className={styles.inspector} aria-label={t("studio.inspector.title")}>
      <header className={styles.header}>
        <h2>{described.display_name}</h2>
        <p className={styles.category}>{t(`studio.rail.category.${described.category}`)}</p>
      </header>

      <section className={styles.licenseSection}>
        <span>{t("studio.inspector.license")}</span>
        <span className="mono">
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
          {download ? (
            <DownloadRow nodeId={described.id} download={download} />
          ) : (
            <Button
              variant="secondary"
              icon="tray"
              onClick={() => {
                void downloads.download(described.id).then(onWeightsChanged);
              }}
            >
              {t("studio.inspector.download", {
                size: formatBytes(described.weights.total_size_bytes),
              })}
            </Button>
          )}
        </section>
      )}

      {!needsAck && !needsDownload && described.weight_manifest.length > 0 && (
        <p className={styles.installed}>
          <Icon name="check" size={12} />
          {t("studio.inspector.installed")}
        </p>
      )}

      <form className={styles.form} onSubmit={(e) => e.preventDefault()}>
        {Object.entries(described.param_schema.properties).map(([name, spec]) => (
          <ParamField
            key={name}
            name={name}
            spec={spec}
            value={selectedNode.data.params[name] ?? spec.default}
            onChange={(value) =>
              onParamsChange(selectedNode.id, { ...selectedNode.data.params, [name]: value })
            }
          />
        ))}

        {described.weight_manifest.length > 0 && (
          <label className={styles.pinnedRow}>
            <input
              type="checkbox"
              checked={selectedNode.data.pinned}
              onChange={(e) => onPinnedChange(selectedNode.id, e.target.checked)}
            />
            <span>{t("studio.inspector.keepLoaded")}</span>
          </label>
        )}
      </form>
    </aside>
  );
}
