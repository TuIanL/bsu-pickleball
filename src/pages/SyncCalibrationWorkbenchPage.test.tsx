import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getCaptureTake: vi.fn(),
  getSyncAnchorStatus: vi.fn(),
  getSyncAnchorDraft: vi.fn(),
  getSyncRecording: vi.fn(),
  getVideoTiming: vi.fn(),
  getVideoStreamUrl: vi.fn(),
  saveSyncAnchorDraft: vi.fn(),
  confirmSyncAnchors: vi.fn(),
}));

vi.mock("../services/analysisClient", () => ({
  getCaptureTake: mocks.getCaptureTake,
  getSyncAnchorStatus: mocks.getSyncAnchorStatus,
  getSyncAnchorDraft: mocks.getSyncAnchorDraft,
  getSyncRecording: mocks.getSyncRecording,
  getVideoTiming: mocks.getVideoTiming,
  getVideoStreamUrl: mocks.getVideoStreamUrl,
  saveSyncAnchorDraft: mocks.saveSyncAnchorDraft,
  confirmSyncAnchors: mocks.confirmSyncAnchors,
  getSyncAnchorExportUrl: (takeId: string) => `/api/capture-takes/${takeId}/sync-anchors/export`,
  isAnalysisApiError: (error: unknown) => Boolean(error && typeof error === "object" && "status" in error),
}));

import { SyncCalibrationWorkbenchPage } from "./SyncCalibrationWorkbenchPage";

const TAKE_ID = "take-workbench";

function status(overrides: Record<string, unknown> = {}) {
  return {
    capture_take_id: TAKE_ID,
    state: "required",
    analysis_allowed: false,
    reason_codes: ["manual_anchors_required"],
    source: "none",
    revision: 0,
    provenance: [],
    invalidation_reasons: [],
    ...overrides,
  };
}

function timing() {
  return {
    schema_version: "video_timing.v1",
    authority: "source_pts",
    frame_count: 3,
    fps: 60,
    first_pts_seconds: 0,
    last_pts_seconds: 100,
    frames: [
      { frame_index: 0, pts_seconds: 0 },
      { frame_index: 1, pts_seconds: 50 },
      { frame_index: 2, pts_seconds: 100 },
    ],
  };
}

function session() {
  return {
    session_id: "sync-session",
    status: "completed",
    camera_slots: {
      cam_1: { camera_id: "camera-a" },
      cam_2: { camera_id: "camera-b" },
    },
    registered_video_ids: { cam_1: "video-a", cam_2: "video-b" },
    segments: [],
    output_dir: "",
    associated_video_paths: [],
    court_name: "测试场",
    match_format: "doubles",
    fps: 60,
    resolution: "1920x1080",
    auto_analyze_after_stop: false,
    duration_sec: 100,
  };
}

function take() {
  return {
    id: TAKE_ID,
    source_session_id: "sync-session",
    capture_mode: "dual",
    field_session_id: "field-1",
    source_session_type: "sync_recording",
    status: "completed",
    started_at: "2026-08-13T00:00:00Z",
    revision: 1,
  };
}

function apiError(statusCode: number, body: object) {
  return { status: statusCode, backendDetail: JSON.stringify(body), message: "request failed" };
}

describe("SyncCalibrationWorkbenchPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.useRealTimers();
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.getCaptureTake.mockResolvedValue(take());
    mocks.getSyncAnchorStatus.mockResolvedValue(status());
    mocks.getSyncAnchorDraft.mockRejectedValue(apiError(404, { code: "draft_not_found" }));
    mocks.getSyncRecording.mockResolvedValue(session());
    mocks.getVideoTiming.mockResolvedValue(timing());
    mocks.getVideoStreamUrl.mockImplementation((videoId: string) => `/video/${videoId}`);
    mocks.saveSyncAnchorDraft.mockResolvedValue({ revision: 1, draft: { ...status(), expected_revision: 1, reference_camera: "camera-a", cameras: ["camera-a", "camera-b"], anchors: [] }, status: status({ state: "draft", revision: 1 }) });
  });

  afterEach(() => cleanup());

  it("restores a server draft before consulting localStorage", async () => {
    const serverAnchor = {
      id: "server-anchor",
      label: "server",
      note: "",
      frame_by_camera: { "camera-a": 1, "camera-b": 1 },
      pts_by_camera: { "camera-a": 50, "camera-b": 50.1 },
      created_at: "2026-08-13T00:00:00Z",
    };
    window.localStorage.setItem(`pre-pickleball-sync-calibration-anchors:${TAKE_ID}`, JSON.stringify([{
      ...serverAnchor,
      id: "local-anchor",
      label: "local",
      frameByCamera: serverAnchor.frame_by_camera,
      ptsByCamera: serverAnchor.pts_by_camera,
    }]));
    mocks.getSyncAnchorDraft.mockResolvedValue({
      capture_take_id: TAKE_ID,
      revision: 3,
      draft: { reference_camera: "camera-a", cameras: ["camera-a", "camera-b"], anchors: [serverAnchor], expected_revision: 3 },
      status: status({ state: "draft", revision: 3 }),
    });

    render(<SyncCalibrationWorkbenchPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    expect(await screen.findByText(/server/)).toBeTruthy();
    expect(screen.queryByText(/local/)).toBeNull();
    expect(screen.getByText(/revision 3/)).toBeTruthy();
  });

  it("offers explicit localStorage import only when the server has no draft", async () => {
    window.localStorage.setItem(`pre-pickleball-sync-calibration-anchors:${TAKE_ID}`, JSON.stringify([{
      id: "local-anchor",
      label: "legacy-local",
      note: "",
      frameByCamera: { "camera-a": 1, "camera-b": 1 },
      ptsByCamera: { "camera-a": 50, "camera-b": 50.1 },
      createdAt: "2026-08-13T00:00:00Z",
    }]));

    render(<SyncCalibrationWorkbenchPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "导入旧浏览器草稿" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "导入旧浏览器草稿" }));
    await waitFor(() => expect(mocks.saveSyncAnchorDraft).toHaveBeenCalled());
    expect(screen.getByText("旧浏览器草稿已导入服务端")).toBeTruthy();
  });

  it("reloads the server version after a save conflict", async () => {
    mocks.getSyncAnchorDraft
      .mockRejectedValueOnce(apiError(404, { code: "draft_not_found" }))
      .mockResolvedValueOnce({
        capture_take_id: TAKE_ID,
        revision: 7,
        draft: { reference_camera: "camera-a", cameras: ["camera-a", "camera-b"], anchors: [], expected_revision: 7 },
        status: status({ state: "draft", revision: 7 }),
      });
    mocks.saveSyncAnchorDraft.mockRejectedValue(apiError(409, { code: "revision_conflict", current_revision: 7 }));

    render(<SyncCalibrationWorkbenchPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);
    await screen.findByText(/当前状态/);
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));

    await waitFor(() => expect(mocks.getSyncAnchorDraft).toHaveBeenCalledTimes(2));
    expect(screen.getByText("草稿版本已变化，已加载最新服务端版本。")).toBeTruthy();
    expect(screen.getByText(/revision 7/)).toBeTruthy();
  });

  it("shows structured confirmation failures and returns after success", async () => {
    const onNavigate = vi.fn();
    const anchors = [0, 50, 100].map((pts, index) => ({
      id: `a-${index}`,
      label: `anchor-${index}`,
      note: "",
      frame_by_camera: { "camera-a": index, "camera-b": index },
      pts_by_camera: { "camera-a": pts, "camera-b": pts + 0.1 },
      created_at: "2026-08-13T00:00:00Z",
    }));
    mocks.getSyncAnchorStatus.mockResolvedValue(status({ revision: 3 }));
    mocks.getSyncAnchorDraft.mockResolvedValue({
      capture_take_id: TAKE_ID,
      revision: 3,
      draft: { reference_camera: "camera-a", cameras: ["camera-a", "camera-b"], anchors, expected_revision: 3 },
      status: status({ state: "draft", revision: 3 }),
    });
    mocks.confirmSyncAnchors.mockRejectedValueOnce(apiError(422, {
      code: "validation_failed",
      issues: [{ code: "coverage_threshold", field: "quality.coverage_ratio", message: "coverage is too narrow" }],
    }));

    render(<SyncCalibrationWorkbenchPage captureTakeId={TAKE_ID} onNavigate={onNavigate} returnPath="/capture/takes/take-workbench/analyze" />);
    await screen.findByText(/当前状态/);
    fireEvent.click(screen.getByRole("button", { name: "提交并确认" }));
    expect(await screen.findByText(/coverage_threshold/)).toBeTruthy();
    expect(onNavigate).not.toHaveBeenCalled();

    mocks.confirmSyncAnchors.mockResolvedValue({ status: status({ state: "confirmed", analysis_allowed: true, revision: 3 }), calibration: {}, anchors: {} });
    fireEvent.click(screen.getByRole("button", { name: "提交并确认" }));
    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith("/capture/takes/take-workbench/analyze"));
  });
});
