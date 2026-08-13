import { describe, expect, it } from "vitest";
import {
  buildAnchorExport,
  clampFrameIndex,
  evaluateAnchorCoverage,
  findNearestFrameIndex,
  getTimingFrame,
  type CalibrationAnchor,
} from "./syncCalibration";

const frames = [
  { frame_index: 0, pts_seconds: 0.033333 },
  { frame_index: 1, pts_seconds: 0.050000 },
  { frame_index: 2, pts_seconds: 0.066667 },
];

describe("sync calibration helpers", () => {
  it("clamps frame stepping to the sidecar boundaries", () => {
    expect(clampFrameIndex(-3, frames)).toBe(0);
    expect(clampFrameIndex(9, frames)).toBe(2);
    expect(getTimingFrame(frames, 1)?.frame_index).toBe(1);
  });

  it("finds the nearest source frame by PTS", () => {
    expect(findNearestFrameIndex(frames, 0.051)).toBe(1);
    expect(findNearestFrameIndex(frames, 0.064)).toBe(2);
  });

  it("exports camera-local PTS in the calibration CLI shape", () => {
    const anchors: CalibrationAnchor[] = [{
      id: "a1",
      label: "击球",
      note: "",
      frameByCamera: { "175": 10, "174": 11 },
      ptsByCamera: { "175": 1.2, "174": 1.25 },
      createdAt: "2026-08-11T00:00:00.000Z",
    }];
    expect(buildAnchorExport("175", ["175", "174"], anchors)).toEqual({
      reference_camera: "175",
      cameras: ["175", "174"],
      anchors: [{ "175": 1.2, "174": 1.25 }],
    });
  });

  it("reports count and early/middle/late coverage", () => {
    const anchors: CalibrationAnchor[] = [0, 50, 100].map((time, index) => ({
      id: `a${index}`,
      label: "",
      note: "",
      frameByCamera: { "175": index, "174": index },
      ptsByCamera: { "175": time, "174": time + 0.05 },
      createdAt: "",
    }));
    const coverage = evaluateAnchorCoverage(anchors, "175", 0, 100);
    expect(coverage.count).toBe(3);
    expect(coverage.spanRatio).toBe(1);
    expect(coverage.hasEarly && coverage.hasMiddle && coverage.hasLate).toBe(true);
  });
});
