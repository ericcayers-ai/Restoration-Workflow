/*
 * The single ARIA live region behind every status readout in the app
 * (UI_DESIGN.md section 6): "the pipeline execution state is exposed via an
 * ARIA live region with plain-language status... not just a visual progress
 * bar." This component *is* that region — Simple Mode's status line and any
 * Studio Mode equivalent both render through it, so there is one accessible
 * announcement path, matching the one WebSocket source of truth for progress
 * (ARCHITECTURE.md section 2).
 */

import styles from "./StatusLine.module.css";
import { Icon } from "./Icon";

type Tone = "neutral" | "active" | "success" | "error";

export function StatusLine({
  message,
  tone = "neutral",
  busy = false,
}: {
  message: string;
  tone?: Tone;
  busy?: boolean;
}) {
  return (
    <p
      className={`${styles.line} ${styles[tone]}`}
      role="status"
      aria-live={tone === "error" ? "assertive" : "polite"}
    >
      {busy ? <Icon name="spinner" size={14} className={styles.spin} /> : null}
      {message}
    </p>
  );
}
