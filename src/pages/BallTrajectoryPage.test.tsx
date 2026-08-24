import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisJobSummary, AnalysisPipelineResult } from "../types/report";
import { BallTrajectoryPage } from "./BallTrajectoryPage";
import * as analysisClient from "../services/analysisClient";

vi.mock("../services/analysisClient", () => ({
  getAnalysisJob: vi.fn(),
  getAnalysisResult: vi.fn(),
  getBallTrajectory: vi.fn(),
  getReconstructedBallTrajectory: vi.fn(),
}));

// BallTrajectoryScene 依赖 Three.js/WebGL，测试中仅验证页面状态与导航，无需真实渲染
vi.mock("../components/platform/BallTrajectoryScene", () => ({
  BallTrajectoryScene: () => <div data-testid="ball-scene" />,
}));

function makeJob(overrides: Partial<AnalysisJobSummary> = {}): AnalysisJobSummary {
  return {
    id: "job-trajectory",
    status: "completed",
    stage: "report",
    progress: 100,
    createdAt: "2026-08-13T00:00:00.000Z",
    updatedAt: "2026-08-13T00:00:00.000Z",
    analysisKind: "multiview",
    analysisMode: "real",
    executionMode: "joint_tracking_v2",
    metadata: {
      fileName: "joint.mp4",
      matchTitle: "Trajectory test",
      venue: "Test court",
      matchDate: "2026-08-13",
      matchFormat: "doubles",
      cameraAngle: "elevated",
      athleteLabel: "Players",
      level: "MVP",
    },
    stages: [],
    ...overrides,
  } as unknown as AnalysisJobSummary;
}

function makeResult(): AnalysisPipelineResult {
  return {
    job_id: "job-trajectory",
    metrics: {},
    artifacts: {},
  } as unknown as AnalysisPipelineResult;
}

function renderPage() {
  return render(<BallTrajectoryPage jobId="job-trajectory" onNavigate={vi.fn()} />);
}

describe("BallTrajectoryPage 空态返回导航", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("无有效球路时展示空态，且提供返回任务管理与返回视觉分析两条返回路径", async () => {
    vi.mocked(analysisClient.getAnalysisJob).mockResolvedValue(makeJob());
    vi.mocked(analysisClient.getAnalysisResult).mockResolvedValue(makeResult());
    vi.mocked(analysisClient.getReconstructedBallTrajectory).mockResolvedValue(null);
    vi.mocked(analysisClient.getBallTrajectory).mockResolvedValue(null);

    renderPage();

    expect(await screen.findByText("暂无可用球路")).toBeTruthy();
    expect(screen.getByRole("button", { name: "返回任务管理" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "返回视觉分析" })).toBeTruthy();
  });

  it("读取失败时展示失败态，仍提供返回任务管理导航", async () => {
    vi.mocked(analysisClient.getAnalysisJob).mockRejectedValue(new Error("backend down"));

    renderPage();

    expect(await screen.findByText("球路读取失败")).toBeTruthy();
    expect(screen.getByRole("button", { name: "返回任务管理" })).toBeTruthy();
  });

  it("没有 v3 URL 但 Parent 已给出 unavailable 状态时展示明确降级说明", async () => {
    vi.mocked(analysisClient.getAnalysisJob).mockResolvedValue(makeJob());
    vi.mocked(analysisClient.getAnalysisResult).mockResolvedValue({
      ...makeResult(),
      artifacts: {
        reconstructed_ball_trajectory_status: "unavailable",
        reconstructed_ball_trajectory_detail: "双摄标定不足，未生成可信球路",
      },
    } as unknown as AnalysisPipelineResult);
    vi.mocked(analysisClient.getReconstructedBallTrajectory).mockResolvedValue(null);
    vi.mocked(analysisClient.getBallTrajectory).mockResolvedValue(null);

    renderPage();

    expect(await screen.findByText("双摄球路暂不可用")).toBeTruthy();
    expect(screen.getAllByText("双摄标定不足，未生成可信球路").length).toBeGreaterThanOrEqual(1);
  });

  it("v4 三维不可用但 display degraded 时仍展示估算球路，且不展示诊断文案", async () => {
    vi.mocked(analysisClient.getAnalysisJob).mockResolvedValue(makeJob());
    vi.mocked(analysisClient.getAnalysisResult).mockResolvedValue(makeResult());
    vi.mocked(analysisClient.getReconstructedBallTrajectory).mockResolvedValue({
      schema_version: "reconstructed_ball_trajectory.v4",
      job_id: "job-trajectory",
      status: "partial",
      detail: "三维不足，已生成估算球路",
      reconstruction_mode: "hybrid_segmented",
      overall_status: "UNAVAILABLE",
      display_trajectory_status: "degraded",
      events: [],
      segments: [{
        segment_id: "flight-1",
        reconstruction_mode: "single_view_event_anchored_2_5d",
        status: "available",
        display_level: "medium",
        metric_validity: "visualization_only",
        anchors: [],
        samples: [
          { frame_index: 1, timestamp_sec: 1, court_xy: [8, 10], estimated_height_ft: 3, source: "detected" },
          { frame_index: 2, timestamp_sec: 1.1, court_xy: [9, 12], estimated_height_ft: 4, source: "interpolated" },
          { frame_index: 3, timestamp_sec: 1.2, court_xy: [10, 14], estimated_height_ft: 0, source: "anchor" },
        ],
      }],
    });

    renderPage();

    expect(await screen.findByTestId("ball-scene")).toBeTruthy();
    expect(screen.queryByText(/估算 2.5D/)).toBeNull();
    expect(screen.queryByText(/环境离群/)).toBeNull();
    expect(screen.queryByText(/可能界外落点/)).toBeNull();
    expect(screen.queryByText("混合分段估算球路")).toBeNull();
    expect(screen.queryByText("双摄球路暂不可用")).toBeNull();
  });
});

describe("BallTrajectoryPage embedded 模式", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("embedded 空态不泄漏旧导航，返回视觉分析走 onSelectView 留在工作区", async () => {
    vi.mocked(analysisClient.getAnalysisJob).mockResolvedValue(makeJob());
    vi.mocked(analysisClient.getAnalysisResult).mockResolvedValue(makeResult());
    vi.mocked(analysisClient.getReconstructedBallTrajectory).mockResolvedValue(null);
    vi.mocked(analysisClient.getBallTrajectory).mockResolvedValue(null);
    const onSelectView = vi.fn();

    render(<BallTrajectoryPage jobId="job-trajectory" onNavigate={vi.fn()} embedded onSelectView={onSelectView} />);

    expect(await screen.findByText("暂无可用球路")).toBeTruthy();
    // 不泄漏「返回任务管理」这类 task-shell 导航
    expect(screen.queryByRole("button", { name: "返回任务管理" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "返回视觉分析" }));
    expect(onSelectView).toHaveBeenCalledWith("analysis");
  });
});
