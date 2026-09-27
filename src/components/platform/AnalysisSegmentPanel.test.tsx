import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import type { AnalysisJobSummary, CaptureSegmentSummary } from "../../types/report";
import { AnalysisSegmentPanel } from "./AnalysisSegmentPanel";

vi.mock("../../services/analysisClient", () => ({
  getCaptureTake: vi.fn(),
  getFormalSegmentationSummary: vi.fn(),
  listSegments: vi.fn(),
}));

import { getCaptureTake, getFormalSegmentationSummary, listSegments } from "../../services/analysisClient";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const job = {
  id: "job-1",
  status: "completed",
  metadata: { capture_take_id: "take-1" },
} as AnalysisJobSummary;

function segment(overrides: Partial<CaptureSegmentSummary>): CaptureSegmentSummary {
  return {
    id: "rally-1",
    capture_take_id: "take-1",
    segment_type: "rally",
    ordinal: 1,
    label: "第1回合",
    start_ms: 1200,
    end_ms: 3400,
    edit_version: 1,
    edit_status: "active",
    status: "closed",
    source: "algorithm",
    segmentation_run_id: "run-1",
    is_highlight: false,
    ...overrides,
  };
}

function renderPanel(overrides: Partial<ComponentProps<typeof AnalysisSegmentPanel>> = {}) {
  const onRallySelect = vi.fn();
  const onPlaybackDataChange = vi.fn();
  render(
    <AnalysisSegmentPanel
      job={job}
      activeRallyId={null}
      onRallySelect={onRallySelect}
      onPlaybackDataChange={onPlaybackDataChange}
      reportActions={[]}
      reportCapability={{ state: "unavailable", reason: "不可用", evidence: { canonicalTracks: false, movementMetrics: false, structuredVisualization: false } }}
      reportPath={(type) => `/reports/${type}`}
      onNavigate={vi.fn()}
      {...overrides}
    />,
  );
  return { onRallySelect, onPlaybackDataChange };
}

describe("AnalysisSegmentPanel", () => {
  it("loads each section independently, keeps manual markers separate, and starts playback from a model rally", async () => {
    vi.mocked(getCaptureTake).mockRejectedValue(new Error("take unavailable"));
    vi.mocked(getFormalSegmentationSummary).mockRejectedValue(new Error("summary unavailable"));
    vi.mocked(listSegments).mockResolvedValue([
      segment({}),
      segment({ id: "manual-1", label: "发球准备", segment_type: "custom", source: "manual", segmentation_run_id: null, ordinal: 0 }),
    ]);
    const { onRallySelect, onPlaybackDataChange } = renderPanel();

    expect(await screen.findByText("第1回合")).toBeTruthy();
    expect(screen.getByText("拍摄阶段人工标记")).toBeTruthy();
    expect(screen.getByText("发球准备")).toBeTruthy();
    expect(screen.getByText("尚未生成正式模型结果。")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /第1回合/ })).toBeNull();
    expect(onRallySelect).not.toHaveBeenCalled();
    await waitFor(() => expect(onPlaybackDataChange).toHaveBeenLastCalledWith([], "正式切分摘要暂不可用"));
  });

  it("shows a specific empty state when the analysis is not associated with a capture take", async () => {
    const onPlaybackDataChange = vi.fn();
    renderPanel({ job: { ...job, metadata: {} } as AnalysisJobSummary, onPlaybackDataChange });
    expect(screen.getByText(/该素材无片段数据/)).toBeTruthy();
    await waitFor(() => expect(onPlaybackDataChange).toHaveBeenLastCalledWith([], "该分析不关联采集片段"));
    expect(getCaptureTake).not.toHaveBeenCalled();
    expect(listSegments).not.toHaveBeenCalled();
    expect(getFormalSegmentationSummary).not.toHaveBeenCalled();
  });

  it("publishes only the current run and starts a selected rally", async () => {
    vi.mocked(getCaptureTake).mockResolvedValue({
      id: "take-1",
      field_session_id: "fs-1",
      source_session_type: "recording",
      source_session_id: "rec-1",
      capture_mode: "single",
      status: "completed",
      started_at: "2026-09-01T00:00:00Z",
      revision: 1,
      duration_ms: 9000,
    });
    vi.mocked(getFormalSegmentationSummary).mockResolvedValue({
      capture_take_id: "take-1",
      status: "succeeded",
      run_id: "run-1",
      model_package_id: "model-1",
      model_version: "1.2.0",
      generated_at: "2026-09-01T01:00:00Z",
      segment_count: 1,
      window_plan_hash: "hash",
      artifact_available: true,
    });
    vi.mocked(listSegments).mockResolvedValue([
      segment({}),
      segment({ id: "old-run", label: "旧回合", segmentation_run_id: "run-old", ordinal: 2 }),
    ]);
    const onRallySelect = vi.fn();
    const onPlaybackDataChange = vi.fn();
    renderPanel({ onRallySelect, onPlaybackDataChange });

    fireEvent.click(await screen.findByRole("button", { name: /第1回合/ }));
    expect(onRallySelect).toHaveBeenCalledWith({ id: "rally-1", ordinal: 1, startMs: 1200, endMs: 3400 });
    expect(screen.queryByText("旧回合")).toBeNull();
    await waitFor(() => expect(onPlaybackDataChange).toHaveBeenLastCalledWith(
      [{ id: "rally-1", ordinal: 1, startMs: 1200, endMs: 3400 }],
      null,
    ));
  });
});
