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
