import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MiniTimeline } from "./MiniTimeline";
import type { CaptureSegmentSummary } from "../types/report";

function makeSeg(overrides: Partial<CaptureSegmentSummary>): CaptureSegmentSummary {
  return {
    id: "seg_test",
    segment_type: "rally",
    ordinal: 1,
    label: "第1分",
    start_ms: 1000,
    end_ms: undefined,
    status: "open",
    source: "manual",
    is_highlight: false,
    edit_version: 1,
    edit_status: "active",
    ...overrides,
  } as CaptureSegmentSummary;
}

describe("MiniTimeline open segment", () => {
  it("renders open segment when end_ms is undefined", () => {
    const seg = makeSeg({ id: "s1", start_ms: 1000, end_ms: undefined, status: "open" });
    render(
      <MiniTimeline
        segments={[seg]}
        events={[]}
        liveState={null}
        totalDurationMs={60000}
        elapsedMs={30000}
      />,
    );
    const ordinals = screen.getAllByText("1");
    expect(ordinals.length).toBeGreaterThanOrEqual(1);
  });

  it("renders closed segment when end_ms is set", () => {
    const seg = makeSeg({ id: "s2", start_ms: 1000, end_ms: 20000, status: "closed" });
    render(
      <MiniTimeline
        segments={[seg]}
        events={[]}
        liveState={null}
        totalDurationMs={60000}
        elapsedMs={30000}
      />,
    );
    const ordinals = screen.getAllByText("1");
    expect(ordinals.length).toBeGreaterThanOrEqual(1);
  });

  it("renders all three track labels", () => {
    const segs = [
      makeSeg({ id: "s1", segment_type: "set", ordinal: 1, label: "第1盘", start_ms: 0, end_ms: 10000, status: "closed" }),
      makeSeg({ id: "s2", segment_type: "game", ordinal: 1, label: "第1局", start_ms: 1000, end_ms: 8000, status: "closed" }),
      makeSeg({ id: "s3", segment_type: "rally", ordinal: 1, label: "第1分", start_ms: 2000, end_ms: 5000, status: "closed" }),
    ];
    render(
      <MiniTimeline
        segments={segs}
        events={[]}
        liveState={null}
        totalDurationMs={60000}
        elapsedMs={30000}
      />,
    );
    expect(screen.getAllByText("盘").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("局").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("分").length).toBeGreaterThanOrEqual(1);
  });

  it("renders empty tracks when no segments", () => {
    render(
      <MiniTimeline
        segments={[]}
        events={[]}
        liveState={null}
        totalDurationMs={60000}
        elapsedMs={10000}
      />,
    );
    expect(screen.getAllByText("盘").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("局").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("分").length).toBeGreaterThanOrEqual(1);
  });

  it("does not show '录制中·持续扩展' text", () => {
    render(
      <MiniTimeline
        segments={[]}
        events={[]}
        liveState={null}
        totalDurationMs={60000}
        elapsedMs={10000}
        showDurationHint={true}
      />,
    );
    expect(screen.queryByText(/录制中·持续扩展/)).toBeNull();
  });
});
