import { describe, expect, it } from "vitest";
import { computeCaptureElapsedMs } from "./captureClock";

describe("computeCaptureElapsedMs", () => {
  it("returns 0 for invalid startedAt", () => {
    expect(computeCaptureElapsedMs("not-a-date", 1000)).toBe(0);
    expect(computeCaptureElapsedMs("", 1000)).toBe(0);
  });

  it("computes elapsed for ISO 8601 with Z suffix", () => {
    const result = computeCaptureElapsedMs("2026-07-17T10:00:00.000Z", new Date("2026-07-17T10:00:35.000Z").getTime());
    expect(result).toBe(35000);
  });

  it("computes elapsed for ISO 8601 with timezone offset", () => {
    const result = computeCaptureElapsedMs("2026-07-17T18:00:00.000+08:00", new Date("2026-07-17T10:00:35.000Z").getTime());
    expect(result).toBe(35000);
  });
});
