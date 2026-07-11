/*
 * The pipeline itself: an ordered list of stages, top runs first. Replaces
 * the node-graph canvas with something that "handles the full stack" without
 * asking a user to think in edges and handles — the list's order *is* the
 * wiring, with the one documented exception in lib/pipelineStages.ts (LaMa's
 * mask input).
 */

import { useT } from "../../lib/i18n";
import type { Stage } from "../../lib/pipelineStages";
import { Button } from "../common/Button";
import { StageRow } from "./StageRow";
import styles from "./StageList.module.css";

export function StageList({
  stages,
  selectedId,
  onSelect,
  onMove,
  onRemove,
  onAutoOrder,
  error,
}: {
  stages: Stage[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onMove: (id: string, direction: -1 | 1) => void;
  onRemove: (id: string) => void;
  onAutoOrder: () => void;
  error: string | null;
}) {
  const t = useT();

  return (
    <div className={styles.wrap}>
      <div className={styles.toolbar}>
        <span className={styles.title}>{t("pipeline.stages.title")}</span>
        <Button
          variant="ghost"
          size="small"
          icon="sort"
          onClick={onAutoOrder}
          disabled={stages.length < 2}
          title={t("pipeline.stages.autoOrderHint")}
        >
          {t("pipeline.stages.autoOrder")}
        </Button>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {stages.length === 0 ? (
        <p className={styles.empty}>{t("pipeline.stages.empty")}</p>
      ) : (
        <ol className={styles.list}>
          {stages.map((stage, index) => (
            <StageRow
              key={stage.id}
              stage={stage}
              index={index}
              count={stages.length}
              selected={stage.id === selectedId}
              onSelect={() => onSelect(stage.id)}
              onMoveUp={() => onMove(stage.id, -1)}
              onMoveDown={() => onMove(stage.id, 1)}
              onRemove={() => onRemove(stage.id)}
            />
          ))}
        </ol>
      )}
    </div>
  );
}
