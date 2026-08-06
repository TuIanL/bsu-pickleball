import { describe, expect, it } from "vitest";
import { isBaselineOrderPlausible } from "./CourtCornerCalibrator";
import type { CalibrationPointDraft } from "./CourtCornerCalibrator";

function makePoint(id: CalibrationPointDraft["id"], y: number): CalibrationPointDraft {
  return { id, label: id, viewX: 0, viewY: y, x: 0, y };
}

function makePoints(farY: number, nearY: number): CalibrationPointDraft[] {
  return [
    makePoint("top_left", farY),
    makePoint("top_right", farY),
    makePoint("bottom_left", nearY),
    makePoint("bottom_right", nearY),
  ];
}

describe("isBaselineOrderPlausible", () => {
  it("accepts near baseline below far baseline", () => {
    expect(isBaselineOrderPlausible(makePoints(100, 500), 720)).toBe(true);
  });

  it("flags reversed baselines", () => {
    expect(isBaselineOrderPlausible(makePoints(500, 100), 720)).toBe(false);
  });

  it("flags near-identical baselines", () => {
    expect(isBaselineOrderPlausible(makePoints(300, 320), 720)).toBe(false);
  });

  it("treats missing points as inconclusive", () => {
    expect(isBaselineOrderPlausible([makePoint("top_left", 100)], 720)).toBe(true);
  });

  it("falls back to a fixed threshold when frame height is unknown", () => {
    // 差值 15px < 默认阈值 20 → 判为可疑
    expect(isBaselineOrderPlausible(makePoints(100, 115), 0)).toBe(false);
    // 差值 25px >= 20 → 合理
    expect(isBaselineOrderPlausible(makePoints(100, 125), 0)).toBe(true);
  });
});
