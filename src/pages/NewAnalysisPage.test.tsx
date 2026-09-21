import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  uploadVideo: vi.fn(),
  createAnalysisJob: vi.fn(),
  rememberAnalysisJob: vi.fn(),
  getVideoStreamUrl: vi.fn(),
  getPlayerBootstrap: vi.fn(),
}));

vi.mock("../services/analysisClient", () => ({
  uploadVideo: mocks.uploadVideo,
  createAnalysisJob: mocks.createAnalysisJob,
  rememberAnalysisJob: mocks.rememberAnalysisJob,
  getVideoStreamUrl: mocks.getVideoStreamUrl,
  getPlayerBootstrap: mocks.getPlayerBootstrap,
}));

vi.mock("../components/platform/CourtCornerCalibrator", () => ({
  CourtCornerCalibrator: ({ onComplete }: { onComplete: (calibrationId: string) => void }) => (
    <button onClick={() => onComplete("cal-1")} type="button">
      完成标定
    </button>
  ),
}));

import { NewAnalysisPage } from "./NewAnalysisPage";

describe("NewAnalysisPage post-create navigation", () => {
  afterEach(() => cleanup());

  it("enters Analysis Progress and materializes a library return when no return is provided", async () => {
    window.history.replaceState({}, "", "/upload?videoId=video-1");
    mocks.getVideoStreamUrl.mockReturnValue("/video/video-1");
    mocks.createAnalysisJob.mockResolvedValue({ id: "job-1" });
    const onNavigate = vi.fn();

    render(<NewAnalysisPage onNavigate={onNavigate} />);

    fireEvent.click(await screen.findByRole("button", { name: "完成标定" }));

    await waitFor(() => expect(onNavigate).toHaveBeenCalledTimes(1));
    expect(mocks.createAnalysisJob).toHaveBeenCalledWith(expect.objectContaining({ useRallyContext: true }));
    const [path, options] = onNavigate.mock.calls[0];
    expect(path).toContain("/analysis/job-1");
    expect(path).toContain(encodeURIComponent("/library/upload/video-1?view=overview"));
    expect(options).toEqual({ replace: true });
  });

  it("forwards an upstream return verbatim instead of materializing a new one", async () => {
    window.history.replaceState(
      {},
      "",
      `/upload?videoId=video-1&return=${encodeURIComponent("/library/upload/existing-video?view=overview")}`,
    );
    mocks.getVideoStreamUrl.mockReturnValue("/video/video-1");
    mocks.createAnalysisJob.mockResolvedValue({ id: "job-2" });
    const onNavigate = vi.fn();

    render(<NewAnalysisPage onNavigate={onNavigate} />);

    fireEvent.click(await screen.findByRole("button", { name: "完成标定" }));

    await waitFor(() => expect(onNavigate).toHaveBeenCalledTimes(1));
    const [path] = onNavigate.mock.calls[0];
    expect(path).toContain("/analysis/job-2");
    expect(path).toContain(encodeURIComponent("/library/upload/existing-video?view=overview"));
    expect(path).not.toContain(encodeURIComponent("/library/upload/video-1?view=overview"));
  });

  it("submits the explicit legacy flow when selected", async () => {
    window.history.replaceState({}, "", "/upload?videoId=video-1");
    mocks.getVideoStreamUrl.mockReturnValue("/video/video-1");
    mocks.createAnalysisJob.mockResolvedValue({ id: "job-legacy" });
    const onNavigate = vi.fn();

    render(<NewAnalysisPage onNavigate={onNavigate} />);
    fireEvent.click(screen.getByTestId("analysis-flow-legacy"));
    fireEvent.click(await screen.findByRole("button", { name: "完成标定" }));

    await waitFor(() => expect(mocks.createAnalysisJob).toHaveBeenCalled());
    expect(mocks.createAnalysisJob).toHaveBeenCalledWith(expect.objectContaining({
      useRallyContext: false,
      rosterConfirmation: { skipped: true, entries: [] },
    }));
  });
});
