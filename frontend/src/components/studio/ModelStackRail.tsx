/*
 * "Left rail — Model Stack. Searchable, grouped by the five categories...
 * Each entry shows name (mono font), category color tab, and a VRAM-tier
 * badge... so a node the user's hardware can't run is visibly greyed rather
 * than silently failing later." (UI_DESIGN.md section 8)
 *
 * Adding a node works two ways: drag onto the canvas (mouse), or click /
 * press Enter on a rail entry (keyboard) — dragging alone would make this
 * feature mouse-only, which UI_DESIGN.md section 6 rules out.
 */

import { useMemo, useState } from "react";
import { useT } from "../../lib/i18n";
import { licenseAbbrev } from "../../lib/format";
import type { DescribedNode, NodeCategory } from "../../lib/types";
import { Icon } from "../common/Icon";
import { RAIL_DRAG_MIME } from "./Canvas";
import styles from "./ModelStackRail.module.css";

const CATEGORY_ORDER: NodeCategory[] = [
  "generative",
  "face",
  "regression",
  "masking",
  "orchestration",
];

export function ModelStackRail({
  nodes,
  onAddNode,
}: {
  nodes: DescribedNode[];
  onAddNode: (nodeTypeId: string) => void;
}) {
  const t = useT();
  const [query, setQuery] = useState("");

  const grouped = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = needle
      ? nodes.filter(
          (n) => n.display_name.toLowerCase().includes(needle) || n.id.includes(needle),
        )
      : nodes;
    const map: Partial<Record<NodeCategory, DescribedNode[]>> = {};
    for (const n of filtered) (map[n.category] ??= []).push(n);
    return map;
  }, [nodes, query]);

  const hasAny = Object.values(grouped).some((list) => list && list.length > 0);

  return (
    <aside className={styles.rail} aria-label={t("studio.rail.title")}>
      <div className={styles.searchRow}>
        <Icon name="loupe" size={14} />
        <input
          className={styles.searchInput}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("studio.rail.search")}
          aria-label={t("studio.rail.search")}
        />
      </div>
      <div className={styles.groups}>
        {!hasAny && <p className={styles.empty}>{t("studio.rail.empty")}</p>}
        {CATEGORY_ORDER.filter((cat) => grouped[cat]?.length).map((cat) => (
          <section key={cat}>
            <h3
              className={styles.categoryTitle}
              style={{ borderLeftColor: `var(--category-${cat})` }}
            >
              {t(`studio.rail.category.${cat}`)}
            </h3>
            <ul className={styles.itemList}>
              {grouped[cat]!.map((node) => (
                <li key={node.id}>
                  <button
                    type="button"
                    className={styles.item}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData(RAIL_DRAG_MIME, node.id)}
                    onClick={() => onAddNode(node.id)}
                    disabled={node.availability.state === "unavailable"}
                    title={
                      node.availability.reason
                        ? t("studio.rail.unavailable", { reason: node.availability.reason })
                        : undefined
                    }
                  >
                    <span className={styles.itemName}>{node.display_name}</span>
                    <span className={styles.badges}>
                      {node.license.requires_acknowledgement && (
                        <span className={styles.licenseBadge} title={node.license.spdx_id}>
                          {licenseAbbrev(node.license.kind)}
                        </span>
                      )}
                      <span className={styles.vramBadge} data-state={node.availability.state}>
                        {t(`studio.rail.vram.${node.vram_tier}`)}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </aside>
  );
}
