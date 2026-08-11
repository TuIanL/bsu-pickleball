import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getAnalysisJob: vi.fn(),
  getAnalysisReport: vi.fn(),
  getAnalysisResult: vi.fn(),
}));

vi.mock("../services/analysisClient", () => ({
  demoAnalysisReport: { reportDefinitions: [], reportActions: [] },
  isAnalysisApiError: () => false,
  getAnalysisJob: mocks.getAnalysisJob,
  getAnalysisReport: mocks.getAnalysisReport,
  getAnalysisResult: mocks.getAnalysisResult,
  getVideoStreamUrl: vi.fn(),
}));

import { ReportPage } from "./ReportPage";
import { VisionPage } from "./VisionPage";

describe("analysis result navigation context", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState({}, "", "/analysis/job-1/vision?taskSource=sync_recording&taskSession=sync-1");
    mocks.getAnalysisJob.mockRejectedValue(new Error("backend offline"));
    mocks.getAnalysisReport.mockResolvedValue(null);
    mocks.getAnalysisResult.mockResolvedValue(null);
  });

  it("keeps the dual-camera context on the vision error return", async () => {
    const onNavigate = vi.fn();
    render(<VisionPage jobId="job-1" onNavigate={onNavigate} />);

    const button = await screen.findByRole("button", { name: "返回任务管理" });
    button.click();
    expect(onNavigate).toHaveBeenCalledWith("/analysis/tasks?source=sync_recording&session=sync-1");
  });

  it("keeps the dual-camera context on the report error return", async () => {
    const onNavigate = vi.fn();
    render(<ReportPage jobId="job-1" reportType="movement" onNavigate={onNavigate} />);

    const button = await screen.findByRole("button", { name: "返回任务管理" });
    button.click();
    expect(onNavigate).toHaveBeenCalledWith("/analysis/tasks?source=sync_recording&session=sync-1");
  });
});
