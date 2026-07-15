import { describe, expect, it } from "vitest";
import {
  downloadSizeBytes,
  formatBytes,
  formatConfidence,
  formatVram,
  licenseAbbrev,
} from "./format";

describe("display formatting", () => {
  it("formatBytes", () => {
    expect(formatBytes(512)).toBe("512B");
    expect(formatBytes(1536)).toBe("1.5KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0MB");
  });

  it("downloadSizeBytes prefers missing variant size", () => {
    expect(
      downloadSizeBytes({ installed: false, total_size_bytes: 100, missing_size_bytes: 40 }),
    ).toBe(40);
    expect(downloadSizeBytes({ installed: true, total_size_bytes: 100, missing_size_bytes: 40 })).toBe(
      100,
    );
  });

  it("formatConfidence and formatVram", () => {
    expect(formatConfidence(0.874)).toBe("87%");
    expect(formatConfidence(undefined)).toBe("");
    expect(formatVram(0)).toBe("—");
    expect(formatVram(2048)).toBe("2GB");
    expect(formatVram(512)).toBe("512MB");
  });

  it("licenseAbbrev", () => {
    expect(licenseAbbrev("non_commercial")).toBe("NC");
    expect(licenseAbbrev("permissive")).toBe("");
  });
});
