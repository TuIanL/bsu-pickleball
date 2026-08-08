import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getCaptureTake: vi.fn(),
  getSyncRecording: vi.fn(),
  getVideoStreamUrl: vi.fn(),
  createMultiviewAnalysisJob: vi.fn(),
  getFusedManifest: vi.fn(),
  getFusionDiagnostics: vi.fn(),
}));

vi.mock("../services/analysisClient", () => ({
  getCaptureTake: mocks.getCaptureTake,
  getSyncRecording: mocks.getSyncRecording,
  getVideoStreamUrl: mocks.getVideoStreamUrl,
  createMultiviewAnalysisJob: mocks.createMultiviewAnalysisJob,
  getFusedManifest: mocks.getFusedManifest,
  getFusionDiagnostics: mocks.getFusionDiagnostics,
}));

vi.mock("../components/platform/CourtCornerCalibrator", () => ({
  CourtCornerCalibrator: () => <div data-testid="calibrator" />,
}));

import { MultiViewAnalysisSetupPage } from "./MultiViewAnalysisSetupPage";

const TAKE_ID = "ct_2fc44dbdc47f";
const SYNC_SESSION_ID = "sync-sess-0001";

function makeTake(sourceSessionId: string) {
  return {
    id: TAKE_ID,
    field_session_id: "fs-1",
    capture_mode: "dual",
    source_session_type: "sync_recording",
    source_session_id: sourceSessionId,
    status: "completed",
    started_at: "2026-08-07T00:00:00.000Z",
    revision: 1,
  };
}

function makeSession(sessionId: string) {
  return {
    session_id: sessionId,
    status: "completed",
    camera_slots: {
      cam_1: { role: "cam_1", camera_id: "camera-a", camera_angle: "baseline", stream_url_snapshot: "" },
      cam_2: { role: "cam_2", camera_id: "camera-b", camera_angle: "baseline", stream_url_snapshot: "" },
    },
    registered_video_ids: { cam_1: "video-a", cam_2: "video-b" },
    court_name: "世园国际匹克球中心",
    match_format: "doubles",
    fps: 60,
    resolution: "1920x1080",
    auto_analyze_after_stop: false,
    segments: [],
    output_dir: "",
    associated_video_paths: [],
    started_at: "2026-08-07T00:00:00.000Z",
    duration_sec: 300,
    capture_take_id: TAKE_ID,
    session_dir: "",
  };
}

describe("MultiViewAnalysisSetupPage", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    mocks.getCaptureTake.mockReset();
    mocks.getSyncRecording.mockReset();
    mocks.getVideoStreamUrl.mockReset();
    mocks.getVideoStreamUrl.mockReturnValue(undefined);
    mocks.getFusedManifest.mockResolvedValue(null);
    mocks.getFusionDiagnostics.mockResolvedValue(null);
  });

  it("uses the ?session= route param (not the take id) to load the sync session", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake("source-fallback-session"));
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    // 关键回归断言：绝不能用 take id 去查 sync 会话（否则 404 "同步录制会话 ct_... 不存在"）
    await waitFor(() => expect(mocks.getSyncRecording).toHaveBeenCalledWith(SYNC_SESSION_ID));
    expect(mocks.getSyncRecording).not.toHaveBeenCalledWith(TAKE_ID);
  });

  it("falls back to take.source_session_id when no ?session= param", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    await waitFor(() => expect(mocks.getSyncRecording).toHaveBeenCalledWith(SYNC_SESSION_ID));
    expect(mocks.getSyncRecording).not.toHaveBeenCalledWith(TAKE_ID);
  });

  it("allows proceeding when videos are ready even if take status is failed", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    // take 状态为 failed，但双视频已注册 → 素材闸只看视频就绪，不看 take.status
    mocks.getCaptureTake.mockResolvedValue({ ...makeTake(SYNC_SESSION_ID), status: "failed" });
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    const nextButton = await screen.findByRole("button", { name: /下一步/ });
    // 素材闸只看视频就绪：take.status=failed 不阻塞（jest-dom 未注册，用 DOM 属性断言）
    expect((nextButton as HTMLButtonElement).disabled).toBe(false);
  });
});
