import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisJobSummary, SyncRecordingSession } from "../types/report";
import { SyncRecordingTaskCard } from "./AnalysisTasksPage";

function makeSession(overrides: Partial<SyncRecordingSession> = {}): SyncRecordingSession {
  return {
    session_id: "sync_1",
    status: "completed",
    camera_slots: {},
    segments: [],
    output_dir: "/tmp/out",
    associated_video_paths: [],
    court_name: "测试球场",
    match_format: "doubles",
    fps: 60,
    resolution: "1920x1080",
    auto_analyze_after_stop: false,
    total_restarts: 0,
    registered_video_ids: { cam_1: "v1", cam_2: "v2" },
    merge_status: "completed",
    capture_take_id: "ct_1",
    ...overrides,
  };
}

function makeJob(id: string, kind = "multiview"): AnalysisJobSummary {
  return {
    id,
    status: "completed",
    stages: [],
    progress: 100,
    createdAt: "2026-08-08T00:00:00.000Z",
    updatedAt: "2026-08-08T00:00:00.000Z",
    analysisKind: kind,
    analysisMode: "real",
    metadata: {
      fileName: "dual.mp4",
      matchTitle: "测试比赛",
      venue: "测试球场",
      matchDate: "2026-08-08",
      matchFormat: "doubles",
      cameraAngle: "baseline",
      athleteLabel: "球采集",
      level: "大众进阶",
    },
  } as unknown as AnalysisJobSummary;
}

function renderCard(props: {
  analysisJobs?: AnalysisJobSummary[];
  deletingAnalysis?: boolean;
  onDeleteAnalysis?: (sessionId: string) => void;
}) {
  const onDeleteAnalysis = props.onDeleteAnalysis ?? vi.fn();
  const utils = render(
    <SyncRecordingTaskCard
      session={makeSession()}
      analysisJobs={props.analysisJobs}
      deletingAnalysis={props.deletingAnalysis ?? false}
      onDeleteAnalysis={onDeleteAnalysis}
      onDelete={vi.fn()}
      onNavigate={vi.fn()}
      onPlay={vi.fn()}
      onMerge={vi.fn()}
    />,
  );
  return { onDeleteAnalysis, ...utils };
}

describe("SyncRecordingTaskCard 删除分析任务", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("有分析任务时显示「删除分析任务」按钮", () => {
    renderCard({ analysisJobs: [makeJob("job-parent")] });
    expect(screen.getByRole("button", { name: /删除分析任务/ })).toBeTruthy();
  });

  it("无分析任务时不显示「删除分析任务」按钮", () => {
    renderCard({ analysisJobs: [] });
    expect(screen.queryByRole("button", { name: /删除分析任务/ })).toBeNull();
  });

  it("点击按钮回调 onDeleteAnalysis 并保留 session id", () => {
    const { onDeleteAnalysis } = renderCard({ analysisJobs: [makeJob("job-parent")] });
    fireEvent.click(screen.getByRole("button", { name: /删除分析任务/ }));
    expect(onDeleteAnalysis).toHaveBeenCalledWith("sync_1");
  });

  it("删除中禁用按钮", () => {
    renderCard({ analysisJobs: [makeJob("job-parent")], deletingAnalysis: true });
    const button = screen.getByRole("button", { name: /删除分析中/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });
});
