import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { StandardCourtPlan } from "./AnalysisDetailsPage";
import type { PipelineTrackPoint } from "../types/report";

function pt(overrides: Partial<PipelineTrackPoint> = {}): PipelineTrackPoint {
  return {
    frame_index: 0,
    timestamp_seconds: 0,
    track_id: "Player_1",
    image_point: { x: 10, y: 10 },
    confidence: 0.9,
    side: "unknown",
    court_point: { x: 10, y: 20 },
    ...overrides,
  };
}

describe("StandardCourtPlan", () => {
  it("does not show '原始 ID' text (replaced by canonical identity)", () => {
    const tracks: PipelineTrackPoint[] = [
      pt({ track_id: "Player_1", court_point: { x: 4, y: 5 } }),
      pt({ track_id: "Player_2", court_point: { x: 16, y: 5 } }),
    ];

    const { container } = render(<StandardCourtPlan tracks={tracks} />);

    expect(container.textContent).not.toContain("原始 ID");
    // "身份" label replaces old "原始 ID"
    expect(container.textContent).toContain("身份");
  });

  it("displays canonical player identifiers P1..P4", () => {
    const tracks: PipelineTrackPoint[] = [
      pt({ track_id: "Player_1", court_point: { x: 4, y: 5 } }),
      pt({ track_id: "Player_2", court_point: { x: 16, y: 5 } }),
    ];

    const { container } = render(<StandardCourtPlan tracks={tracks} />);

    // Canonical labels appear
    expect(container.textContent).toContain("P1");
    expect(container.textContent).toContain("P2");
  });

  it("does not reference raw track_id reassignment in fragment text", () => {
    const tracks: PipelineTrackPoint[] = [
      pt({ track_id: "Player_1", court_point: { x: 4, y: 5 } }),
    ];

    const { container } = render(<StandardCourtPlan tracks={tracks} />);

    // Text no longer mentions "重新分配 ID"
    expect(container.textContent).not.toContain("重新分配 ID");
    // Updated text mentions "跟丢重连" instead
    expect(container.textContent).toContain("跟丢重连");
  });

  it("shows '—' for non-canonical track_ids (defensive)", () => {
    const tracks: PipelineTrackPoint[] = [
      pt({ track_id: "164", court_point: { x: 10, y: 20 } }),
    ];

    const { container } = render(<StandardCourtPlan tracks={tracks} />);

    // Non-canonical track_id: formatPlayerId returns "" → fallback "—"
    expect(container.textContent).toMatch(/—/);
    expect(container.textContent).not.toContain("ID 164");
  });
});
