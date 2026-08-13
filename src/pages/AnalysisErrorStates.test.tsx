import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalysisJobSummary } from "../types/report";

const analysisClientMocks = vi.hoisted(() => ({
  getAnalysisJob: vi.fn(),
  getAnalysisReport: vi.fn(),
  getAnalysisResult: vi.fn(),
}));

const { getAnalysisJob, getAnalysisReport, getAnalysisResult } = analysisClientMocks;

vi.mock("../services/analysisClient", () => ({
  demoAnalysisReport: { reportDefinitions: [], reportActions: [] },
  isAnalysisApiError: () => false,
  getAnalysisJob: analysisClientMocks.getAnalysisJob,
  getAnalysisReport: analysisClientMocks.getAnalysisReport,
  getAnalysisResult: analysisClientMocks.getAnalysisResult,
  getVideoStreamUrl: () => undefined,
}));

import { AnalysisDetailsPage } from "./AnalysisDetailsPage";

const onNavigate = vi.fn();

function failedJob(): AnalysisJobSummary {
  return {
    id: "job-failed",
    status: "failed",
    stage: "video-read",
    progress: 18,
    createdAt: "2026-08-03T00:00:00.000Z",
    updatedAt: "2026-08-03T00:01:00.000Z",
    metadata: {
      fileName: "broken.mp4",
      matchTitle: "失败任务",
      venue: "测试球场",
      matchDate: "2026-08-03",
      matchFormat: "doubles",
      cameraAngle: "baseline",
      athleteLabel: "Player A",
      level: "MVP",
    },
    stages: [],
    errorCode: "VIDEO_READ_FAILED",
    publicErrorMessage: "视频读取失败",
  };
}

describe("analysis task error states", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    onNavigate.mockReset();
  });

  it("shows a visible error when the analysis API is unavailable", async () => {
    getAnalysisJob.mockRejectedValue(new Error("backend offline"));
    getAnalysisReport.mockResolvedValue(null);
    getAnalysisResult.mockResolvedValue(null);

    render(<AnalysisDetailsPage jobId="job-network-error" onNavigate={onNavigate} />);

    expect(await screen.findByRole("heading", { name: "读取分析结果失败" })).toBeTruthy();
  });

  it("shows the real failed task state instead of demo content", async () => {
    getAnalysisJob.mockResolvedValue(failedJob());
    getAnalysisReport.mockResolvedValue(null);
    getAnalysisResult.mockResolvedValue(null);

    render(<AnalysisDetailsPage jobId="job-failed" onNavigate={onNavigate} />);

    expect(await screen.findByRole("heading", { name: "分析任务失败" })).toBeTruthy();
    expect(screen.getAllByText("视频读取失败").length).toBeGreaterThan(0);
  });

  it("returns a multiview failure to the dual-camera task list", async () => {
    getAnalysisJob.mockResolvedValue({ ...failedJob(), analysisKind: "multiview", recordingSessionId: "sync-1" });
    getAnalysisReport.mockResolvedValue(null);
    getAnalysisResult.mockResolvedValue(null);
    window.history.replaceState({}, "", "/analysis/job-failed");

    render(<AnalysisDetailsPage jobId="job-failed" onNavigate={onNavigate} />);

    expect(await screen.findByRole("heading", { name: "分析任务失败" })).toBeTruthy();
    const returnButton = await screen.findByRole("button", { name: "返回任务管理" });
    returnButton.click();
    expect(onNavigate).toHaveBeenCalledWith("/analysis/tasks?source=sync_recording&session=sync-1");
  });
});
