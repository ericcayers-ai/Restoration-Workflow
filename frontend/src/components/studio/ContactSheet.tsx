/*
 * "Bottom strip — Contact sheet. A thumbnail history of runs on the current
 * image (or batch), literally a contact-sheet grid, click to recall any
 * prior result or fork a new pipeline from it." (UI_DESIGN.md section 8)
 */

import { jobResultUrl } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { Job } from "../../lib/types";
import { Icon } from "../common/Icon";
import styles from "./ContactSheet.module.css";

export interface RunRecord {
  job: Job;
}

export function ContactSheet({
  runs,
  onFork,
}: {
  runs: RunRecord[];
  onFork: (job: Job) => void;
}) {
  const t = useT();

  return (
    <div className={styles.strip} aria-label={t("studio.contactSheet.title")}>
      <span className={styles.title}>{t("studio.contactSheet.title")}</span>
      {runs.length === 0 && <p className={styles.empty}>{t("studio.contactSheet.empty")}</p>}
      {runs.map(({ job }) => (
        <button
          key={job.id}
          type="button"
          className={styles.frame}
          data-state={job.state}
          onClick={() => onFork(job)}
          title={t("studio.contactSheet.recall")}
        >
          {job.state === "done" ? (
            <img src={jobResultUrl(job.id)} alt="" />
          ) : (
            <div className={styles.spinner}>
              <Icon name={job.state === "error" ? "warning" : "spinner"} size={18} />
            </div>
          )}
          <span className={styles.frameLabel}>
            {job.pipeline.nodes.map((n) => n.type).join(" > ")}
          </span>
        </button>
      ))}
    </div>
  );
}
