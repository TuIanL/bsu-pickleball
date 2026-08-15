import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AutomaticCalibrationResponse } from "../../types/report";
import { buildDefaultQuadPoints, isBaselineOrderPlausible } from "./CourtCornerCalibrator";
import type { CalibrationPointDraft } from "./CourtCornerCalibrator";

const mocks = vi.hoisted(() => ({
  requestAutomaticCalibration: vi.fn(),
  acceptAutomaticCalibration: vi.fn(),
  createManualCalibration: vi.fn(),
}));

vi.mock("../../services/analysisClient", () => ({
  requestAutomaticCalibration: mocks.requestAutomaticCalibration,
  acceptAutomaticCalibration: mocks.acceptAutomaticCalibration,
  createManualCalibration: mocks.createManualCalibration,
  resolveAnalysisAssetUrl: () => undefined,
  isAnalysisApiError: () => false,
}));

import { CourtCornerCalibrator } from "./CourtCornerCalibrator";

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

function availableResponse(): AutomaticCalibrationResponse {
  return {
    status: "available",
    detail: "ok",
    keypoints: {
      top_left: { x: 20, y: 20 },
      top_right: { x: 80, y: 20 },
      bottom_right: { x: 80, y: 80 },
      bottom_left: { x: 20, y: 80 },
    },
    selected_frame: { video_id: "video-1", frame_index: 15, timestamp_seconds: 0.5, width: 100, height: 100 },
    mask: { model_configured: true, confidence: 0.9, line_count: 4, detail: "ok" },
  };
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
    expect(isBaselineOrderPlausible(makePoints(100, 115), 0)).toBe(false);
    expect(isBaselineOrderPlausible(makePoints(100, 125), 0)).toBe(true);
  });
});

describe("buildDefaultQuadPoints", () => {
  it("returns four corners in the fixed calibration order", () => {
    const points = buildDefaultQuadPoints(1000, 500);
    expect(points.map((point) => point.id)).toEqual(["top_left", "top_right", "bottom_right", "bottom_left"]);
  });

  it("centers the default quad with margins", () => {
    const points = buildDefaultQuadPoints(1000, 500);
    expect(points[0].x).toBe(220); // 0.22 * 1000
    expect(points[0].y).toBe(90); // 0.18 * 500
    expect(points[2].x).toBe(780); // 0.78 * 1000
    expect(points[2].y).toBe(410); // 0.82 * 500
  });
});

describe("CourtCornerCalibrator auto-trigger", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("auto-triggers automatic calibration once on mount with the near-start frame hint", async () => {
    mocks.requestAutomaticCalibration.mockResolvedValue(availableResponse());

    render(<CourtCornerCalibrator videoSrc="blob:fake" videoId="video-1" onComplete={vi.fn()} />);

    await waitFor(() => expect(mocks.requestAutomaticCalibration).toHaveBeenCalledTimes(1));
    expect(mocks.requestAutomaticCalibration).toHaveBeenCalledWith("video-1", { timestampSeconds: 0.5 });
  });

  it("falls back to manual drag when automatic calibration is unavailable", async () => {
    mocks.requestAutomaticCalibration.mockResolvedValue({
      status: "unavailable",
      detail: "no model",
      mask: { model_configured: false, line_count: 0, detail: "no model" },
    });

    render(<CourtCornerCalibrator videoSrc="blob:fake" videoId="video-1" onComplete={vi.fn()} />);

    expect(await screen.findByText(/自动标定失败，已切换到人工标定/)).toBeTruthy();
  });
});
