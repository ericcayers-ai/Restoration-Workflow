/*
 * Compact step rail for Simple Mode — orients the user without competing
 * with the photo. One job: show where you are in Drop → Review → Restore.
 */

import { Icon } from "./Icon";
import styles from "./FlowSteps.module.css";

export type FlowStepId = "drop" | "review" | "restore";

export function FlowSteps({
  steps,
  current,
  labels,
  complete = false,
  ariaLabel,
}: {
  steps: FlowStepId[];
  current: FlowStepId;
  labels: Record<FlowStepId, string>;
  /** When true, every step is marked done (result screen). */
  complete?: boolean;
  ariaLabel: string;
}) {
  const currentIndex = complete ? steps.length : steps.indexOf(current);
  return (
    <ol className={styles.rail} aria-label={ariaLabel}>
      {steps.map((id, index) => {
        const state =
          index < currentIndex ? "done" : index === currentIndex ? "current" : "upcoming";
        return (
          <li key={id} className={styles.step} data-state={state}>
            <span className={styles.marker} aria-hidden>
              {state === "done" ? <Icon name="check" size={10} /> : index + 1}
            </span>
            <span className={styles.label}>{labels[id]}</span>
            {index < steps.length - 1 ? <span className={styles.connector} aria-hidden /> : null}
          </li>
        );
      })}
    </ol>
  );
}
