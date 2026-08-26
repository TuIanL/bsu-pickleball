import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ScoringCalibrationTimeline } from "./ScoringCalibrationTimeline";

describe("ScoringCalibrationTimeline", () => {
  it("展示回合、候选和人工标记并可定位事件", () => {
    const onSelectCandidate = vi.fn();
    const onSelectAnnotation = vi.fn();
    const onSeek = vi.fn();

    render(
      <ScoringCalibrationTimeline
        segments={[{
          id: "rally-1", capture_take_id: "take-1", segment_type: "rally", ordinal: 1, label: "第1分",
          start_ms: 0, end_ms: 2000, effective_start_ms: 0, effective_end_ms: 2000,
          edit_version: 0, edit_status: "active", status: "closed", source: "manual", is_highlight: false,
        }]}
        annotations={[{
          id: "ann-1", package_revision_id: "rev-1", source: "manual", event_ms: 1200,
          evidence_start_ms: 1000, evidence_end_ms: 1400, stage: "serve", outcome: "in_play",
          decision: "accepted", revoked: false, created_at: "", updated_at: "",
        }]}
        candidates={[{
          candidate_id: "candidate-1", candidate_type: "serve", source: "algorithm", timestamp_ms: 800,
          payload: {}, decision: "unreviewed",
        }]}
        totalDurationMs={3000}
        currentTimeMs={1000}
        onSeek={onSeek}
        onSelectAnnotation={onSelectAnnotation}
        onSelectCandidate={onSelectCandidate}
      />,
    );

    expect(screen.getByText("标注时间线")).toBeTruthy();
    expect(screen.getByTitle("算法候选 0:00")).toBeTruthy();
    expect(screen.getByTitle("人工标注 0:01")).toBeTruthy();
    fireEvent.click(screen.getByTitle("算法候选 0:00"));
    expect(onSelectCandidate).toHaveBeenCalledWith(expect.objectContaining({ candidate_id: "candidate-1" }));
    fireEvent.click(screen.getByTitle("人工标注 0:01"));
    expect(onSelectAnnotation).toHaveBeenCalledWith(expect.objectContaining({ id: "ann-1" }));
  });
});
