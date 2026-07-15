export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)}${units[unitIndex]}`;
}

/** Prefer missing default-variant size when reporting download totals. */
export function downloadSizeBytes(weights: {
  installed: boolean;
  total_size_bytes: number;
  missing_size_bytes?: number;
}): number {
  if (weights.installed) return weights.total_size_bytes;
  if (weights.missing_size_bytes != null && weights.missing_size_bytes > 0) {
    return weights.missing_size_bytes;
  }
  return weights.total_size_bytes;
}

/** Confidence label for analyzer reasons (0–1 → percent string). */
export function formatConfidence(value: number | undefined): string {
  if (value == null || Number.isNaN(value)) return "";
  return `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%`;
}


export function formatVram(mb: number): string {
  if (mb <= 0) return "—";
  return mb >= 1024 ? `${(mb / 1024).toFixed(mb % 1024 === 0 ? 0 : 1)}GB` : `${mb}MB`;
}

/** Short, color-independent badge text for a non-permissive license
 *  (UI_DESIGN.md section 6: color is never the sole carrier of meaning). */
export function licenseAbbrev(kind: "permissive" | "non_commercial" | "unclear" | "custom"): string {
  switch (kind) {
    case "non_commercial":
      return "NC";
    case "unclear":
      return "?";
    case "custom":
      return "C";
    case "permissive":
      return "";
  }
}

/** Accessible explanation for NC / Restricted badges in Settings and the rail. */
export function licenseBadgeHint(kind: "permissive" | "non_commercial" | "unclear" | "custom"): string {
  switch (kind) {
    case "non_commercial":
      return "Non-commercial licence: download and run locally after acknowledgement. Not used by Simple Mode Auto.";
    case "unclear":
      return "Restricted / unverified licence: opt-in only after acknowledgement. Not used by Simple Mode Auto.";
    case "custom":
      return "Custom upstream licence: opt-in only after acknowledgement.";
    case "permissive":
      return "";
  }
}
