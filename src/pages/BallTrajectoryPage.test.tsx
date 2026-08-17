import { cleanup, render, screen } from "@testing-library/react";
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
});
