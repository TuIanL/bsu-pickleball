import { describe, expect, it } from "vitest";
import { canonicalTimeToSourceTimeMs, resolveDisplayViewId, sourceTimeToCanonicalTimeMs, withDisplayViewQuery } from "./multiviewDisplay";

describe("multiview display view URL contract", () => {
  it("非法或缺失机位回退 reference view", () => {
    expect(resolveDisplayViewId("cam_2", ["cam_1", "cam_2"], "cam_1")).toBe("cam_2");
    expect(resolveDisplayViewId("cam_2", ["cam_1"], "cam_1")).toBe("cam_1");
    expect(resolveDisplayViewId("cam_x", ["cam_1", "cam_2"], "cam_1")).toBe("cam_1");
    expect(resolveDisplayViewId(null, ["cam_1", "cam_2"], "cam_1")).toBe("cam_1");
  });

  it("只替换 displayView 并保留 workspace view 与 analysisJob", () => {
    expect(withDisplayViewQuery(
      "/library/sync_recording/s-1?view=analysis&analysisJob=j-1&displayView=cam_1#top",
      "cam_2",
    )).toBe("/library/sync_recording/s-1?view=analysis&analysisJob=j-1&displayView=cam_2#top");
  });

  it("canonical 时间切换视角时按目标媒体映射恢复", () => {
    const mapping = { offsetMs: 250, rate: 1.02 };
    expect(canonicalTimeToSourceTimeMs(10000, mapping)).toBe(10450);
    expect(sourceTimeToCanonicalTimeMs(10450, mapping)).toBeCloseTo(10000);
  });

  it("同一 canonical 时间分别映射到 A/B source 时间并可逆", () => {
    const canonicalTimeMs = 12_500;
    const cam1 = { offsetMs: 0, rate: 1 };
    const cam2 = { offsetMs: 83, rate: 0.998 };
    const cam1Source = canonicalTimeToSourceTimeMs(canonicalTimeMs, cam1);
    const cam2Source = canonicalTimeToSourceTimeMs(canonicalTimeMs, cam2);

    expect(cam1Source).toBe(12_500);
    expect(cam2Source).toBeCloseTo(12_558, 5);
    expect(sourceTimeToCanonicalTimeMs(cam1Source, cam1)).toBeCloseTo(canonicalTimeMs);
    expect(sourceTimeToCanonicalTimeMs(cam2Source, cam2)).toBeCloseTo(canonicalTimeMs);
  });
});
