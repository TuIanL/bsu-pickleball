import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisJobSummary } from "../types/report";
import { demoAnalysisReport } from "../data/demoData";
import { VisionPage } from "./VisionPage";
import * as analysisClient from "../services/analysisClient";

vi.mock("../services/analysisClient", () => ({
  getAnalysisJob: vi.fn(),
  getAnalysisReport: vi.fn(),
  getAnalysisResult: vi.fn(),
  getVideoStreamUrl: vi.fn(() => "/stream"),
  getStructuredVizData: vi.fn(() => Promise.resolve(null)),
  resolveAnalysisAssetUrl: vi.fn((url: string) => url),
  getBallTrajectory: vi.fn(() => Promise.resolve(null)),
  getBounceEvents: vi.fn(() => Promise.resolve(null)),
  getPoseOverlay: vi.fn(() => Promise.resolve(null)),
  getServeEvents: vi.fn(() => Promise.resolve(null)),
  getTrackingOverlay: vi.fn(() => Promise.resolve(null)),
  getFusedPlayerOverlay: vi.fn(() => Promise.resolve(null)),
  getAnalysisOverlayVideoUrl: vi.fn(() => undefined),
  getPositionHeatmaps: vi.fn(() => Promise.resolve(null)),
  getPositionScatterPlots: vi.fn(() => Promise.resolve(null)),
}));

// 重型展示组件在本次测试中不关心，渲染为空避免额外依赖
vi.mock("../components/platform/VideoAnalysisCard", () => ({ VideoAnalysisCard: () => <div /> }));
vi.mock("../components/platform/PlayerScoringPanel", () => ({ PlayerScoringPanel: () => <div /> }));
vi.mock("../components/platform/MetricCard", () => ({ MetricCard: () => <div /> }));
vi.mock("../components/platform/SkillRatings", () => ({ SkillRatings: () => <div /> }));
vi.mock("../components/RecommendedDrills", () => ({ RecommendedDrills: () => <div /> }));
vi.mock("../components/platform/ProgressChart", () => ({ ProgressChart: () => <div /> }));
vi.mock("../components/platform/StructuredHeatmap", () => ({ default: () => <div /> }));
vi.mock("../components/platform/StructuredScatterPlot", () => ({ default: () => <div /> }));
vi.mock("../components/platform/StructuredZoneHeatmap", () => ({ default: () => <div /> }));
vi.mock("../components/RailMeta", () => ({ RailMeta: () => <div /> }));

function makeJob(overrides: Partial<AnalysisJobSummary> = {}): AnalysisJobSummary {
  return {
    id: "job-vision",
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
      matchTitle: "Vision test",
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

function renderPage(job: AnalysisJobSummary) {
  vi.mocked(analysisClient.getAnalysisJob).mockResolvedValue(job);
  vi.mocked(analysisClient.getAnalysisReport).mockResolvedValue(demoAnalysisReport);
  vi.mocked(analysisClient.getAnalysisResult).mockResolvedValue(null);
  const onNavigate = vi.fn();
  render(<VisionPage jobId={job.id} onNavigate={onNavigate} recentJob={null} />);
  return { onNavigate };
}

describe("VisionPage 双摄协同详情快捷入口", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("双摄协同完成态展示入口，点击直达协同详情", async () => {
    const { onNavigate } = renderPage(makeJob());
    const button = await screen.findByRole("button", { name: "查看双摄协同详情" });
    fireEvent.click(button);
    expect(onNavigate).toHaveBeenCalledWith(
      expect.stringContaining("/analysis/job-vision/multiview"),
    );
    expect(screen.getByRole("button", { name: "查看球路" })).toBeTruthy();
  });

  it("非双摄协同任务不展示入口", async () => {
    renderPage(makeJob({ analysisKind: "single_view" }));
    await screen.findByRole("button", { name: "查看球路" });
    expect(screen.queryByRole("button", { name: "查看双摄协同详情" })).toBeNull();
  });

  it("双摄协同未完成时不展示入口", async () => {
    renderPage(makeJob({ status: "processing", progress: 40 }));
    expect(await screen.findByText(/任务还在排队或处理中/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "查看双摄协同详情" })).toBeNull();
  });
});
