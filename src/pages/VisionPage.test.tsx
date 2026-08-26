import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisJobSummary, AnalysisPipelineResult } from "../types/report";
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
  getShotRallyEvents: vi.fn(() => Promise.resolve(null)),
}));

// 重型展示组件在本次测试中不关心，渲染为空避免额外依赖
vi.mock("../components/platform/VideoAnalysisCard", () => ({ VideoAnalysisCard: () => <div data-testid="video-analysis-card" /> }));
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
    expect(screen.queryByText("双摄球路分析")).toBeNull();
    expect(screen.queryByText("六维雷达评分")).toBeNull();
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

  it("嵌入式视频分析在无有效报告证据时禁用下级报告且不触发 view 切换", async () => {
    const result = {
      job_id: "job-vision", status: "completed", generated_at: "2026-08-13T00:00:00.000Z",
      tracks: [],
      metrics: { distances: [], speeds: [], kitchen_dwell: [], doubles_spacing: [], heatmap: { rows: 0, cols: 0, cells: [] } },
      artifacts: {}, message: "no evidence", stages: [],
    } as unknown as AnalysisPipelineResult;
    vi.mocked(analysisClient.getAnalysisJob).mockResolvedValue(makeJob());
    vi.mocked(analysisClient.getAnalysisReport).mockResolvedValue(demoAnalysisReport);
    vi.mocked(analysisClient.getAnalysisResult).mockResolvedValue(result);
    const onSelectView = vi.fn();
    render(<VisionPage jobId="job-vision" onNavigate={vi.fn()} recentJob={null} embedded onSelectView={onSelectView} />);

    const reportButton = await screen.findByRole("button", { name: "本场表现报告" }) as HTMLButtonElement;
    expect(reportButton.disabled).toBe(true);
    fireEvent.click(reportButton);
    expect(onSelectView).not.toHaveBeenCalled();
  });

  it("时序 artifact 读取失败时保留视频、任务状态和原有位置图卡片", async () => {
    const result = {
      job_id: "job-vision",
      status: "completed",
      generated_at: "2026-08-13T00:00:00.000Z",
      tracks: [],
      metrics: {
        distances: [],
        speeds: [],
        kitchen_dwell: [],
        doubles_spacing: [],
        heatmap: { rows: 0, cols: 0, cells: [] },
      },
      artifacts: { shot_rally_events_url: "/api/analysis/jobs/job-vision/artifacts/shot-rally-events" },
    } as unknown as AnalysisPipelineResult;
    const job = makeJob({ analysisKind: "single_view" });
    vi.mocked(analysisClient.getAnalysisJob).mockResolvedValue(job);
    vi.mocked(analysisClient.getAnalysisReport).mockResolvedValue(demoAnalysisReport);
    vi.mocked(analysisClient.getAnalysisResult).mockResolvedValue(result);
    vi.mocked(analysisClient.getShotRallyEvents).mockRejectedValue(new Error("malformed artifact"));

    render(<VisionPage jobId={job.id} onNavigate={vi.fn()} recentJob={null} />);

    expect(await screen.findByText("回合—击球阶段时序图")).toBeTruthy();
    expect(await screen.findByText("读取失败")).toBeTruthy();
    expect(screen.getByText("视频分析结果")).toBeTruthy();
    expect(screen.getByTestId("video-analysis-card")).toBeTruthy();
    expect(screen.getByText("分析完成")).toBeTruthy();
    expect(screen.getAllByText("位置热力图").length).toBeGreaterThan(0);
    expect(screen.getAllByText("位置散点图").length).toBeGreaterThan(0);
    expect(screen.getByText("区域空间热力图")).toBeTruthy();
  });
});
