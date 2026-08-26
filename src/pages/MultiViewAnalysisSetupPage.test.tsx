import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getCaptureTake: vi.fn(),
  getMetricCourtSceneDraft: vi.fn(),
  saveMetricCourtSceneDraft: vi.fn(),
  validateMetricCourtScene: vi.fn(),
  publishMetricCourtScene: vi.fn(),
  getSyncAnchorStatus: vi.fn(),
  getSyncRecording: vi.fn(),
  getVideoStreamUrl: vi.fn(),
  createMultiviewAnalysisJob: vi.fn(),
  getFusedManifest: vi.fn(),
  getFusionDiagnostics: vi.fn(),
}));

vi.mock("../services/analysisClient", () => ({
  getCaptureTake: mocks.getCaptureTake,
  getMetricCourtSceneDraft: mocks.getMetricCourtSceneDraft,
  saveMetricCourtSceneDraft: mocks.saveMetricCourtSceneDraft,
  validateMetricCourtScene: mocks.validateMetricCourtScene,
  publishMetricCourtScene: mocks.publishMetricCourtScene,
  getSyncAnchorStatus: mocks.getSyncAnchorStatus,
  getSyncRecording: mocks.getSyncRecording,
  getVideoStreamUrl: mocks.getVideoStreamUrl,
  createMultiviewAnalysisJob: mocks.createMultiviewAnalysisJob,
  isAnalysisApiError: () => false,
  getFusedManifest: mocks.getFusedManifest,
  getFusionDiagnostics: mocks.getFusionDiagnostics,
}));

vi.mock("../components/platform/CourtCornerCalibrator", () => ({
  CourtCornerCalibrator: (props: {
    videoId: string;
    initialPoints?: unknown[];
    cancelLabel?: string;
    onCancel?: () => void;
    onComplete: (calibrationId: string, points: unknown[]) => void;
  }) => (
    <div data-testid={`calibrator-${props.videoId}`}>
      <span data-testid={`draft-count-${props.videoId}`}>{props.initialPoints?.length ?? 0}</span>
      <button onClick={props.onCancel} type="button">{props.cancelLabel ?? "取消"}</button>
      <button onClick={() => props.onComplete(`cal-${props.videoId}`, [
        { id: "top_left", label: "远端左角", viewX: 10, viewY: 10, x: 10, y: 10 },
        { id: "top_right", label: "远端右角", viewX: 90, viewY: 10, x: 90, y: 10 },
        { id: "bottom_right", label: "近端右角", viewX: 90, viewY: 90, x: 90, y: 90 },
        { id: "bottom_left", label: "近端左角", viewX: 10, viewY: 90, x: 10, y: 90 },
      ])} type="button">完成标定 {props.videoId}</button>
    </div>
  ),
}));

vi.mock("../components/platform/NetProfileCalibrator", () => ({
  HOLDOUT_ORDER: [
    { id: "holdout_left_quarter", label: "左四分之一点", x: 5 },
    { id: "holdout_right_quarter", label: "右四分之一点", x: 15 },
  ],
  estimateNetProfileHeight: (profile: { control_points: Array<{ world: { z: number } }> }) => profile.control_points[1]?.world.z ?? 0,
  NetProfileCalibrator: (props: { viewId: string; onCancel: () => void; onComplete: (draft: unknown) => void }) => (
    <div data-testid={`net-calibrator-${props.viewId}`}>
      <button onClick={props.onCancel} type="button">上一步</button>
      <button onClick={() => props.onComplete({
        profile: {
          profile_type: "standard",
          height_source: "standard",
          coordinate_units: "feet",
          control_points: [
            { id: "left", world: { x: 0, y: 22, z: 3 }, confirmed: true },
            { id: "center", world: { x: 10, y: 22, z: 34 / 12 }, confirmed: true },
            { id: "right", world: { x: 20, y: 22, z: 3 }, confirmed: true },
          ],
          sampled_top_profile: [],
        },
        annotations: { left: { x: 100, y: 200 }, center: { x: 320, y: 180 }, right: { x: 540, y: 200 } },
        holdoutAnnotations: { holdout_left_quarter: { x: 210, y: 190 }, holdout_right_quarter: { x: 430, y: 190 } },
        imageWidth: 640,
        imageHeight: 360,
        frameIndex: 30,
      })} type="button">完成球网 {props.viewId}</button>
    </div>
  ),
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

function makeSyncStatus(overrides: Record<string, unknown> = {}) {
  return {
    capture_take_id: TAKE_ID,
    state: "confirmed",
    analysis_allowed: true,
    reason_codes: ["manual_confirmation_valid"],
    source: "manual_anchors",
    revision: 4,
    provenance: [],
    invalidation_reasons: [],
    quality: {
      anchor_count: 4,
      coverage_ratio: 0.8,
      residual_rms_ms: 4,
      quality: "good",
    },
    ...overrides,
  };
}

function makeSession(sessionId: string, overrides: Record<string, unknown> = {}) {
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
    ...overrides,
  };
}

describe("MultiViewAnalysisSetupPage", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    mocks.getCaptureTake.mockReset();
    mocks.getMetricCourtSceneDraft.mockReset();
    mocks.saveMetricCourtSceneDraft.mockReset();
    mocks.validateMetricCourtScene.mockReset();
    mocks.publishMetricCourtScene.mockReset();
    mocks.getSyncAnchorStatus.mockReset();
    mocks.getSyncRecording.mockReset();
    mocks.getVideoStreamUrl.mockReset();
    mocks.createMultiviewAnalysisJob.mockReset();
    mocks.getVideoStreamUrl.mockImplementation((videoId: string) => `/video/${videoId}`);
    mocks.getMetricCourtSceneDraft.mockResolvedValue(null);
    mocks.saveMetricCourtSceneDraft.mockImplementation((_takeId: string, payload: unknown) => Promise.resolve(payload));
    mocks.validateMetricCourtScene.mockResolvedValue({ status: "ready", rejection_reasons: [] });
    mocks.publishMetricCourtScene.mockResolvedValue({ revision: 1 });
    mocks.getFusedManifest.mockResolvedValue(null);
    mocks.getFusionDiagnostics.mockResolvedValue(null);
  });

  it("uses the ?session= route param (not the take id) to load the sync session", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake("source-fallback-session"));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    // 关键回归断言：绝不能用 take id 去查 sync 会话（否则 404 "同步录制会话 ct_... 不存在"）
    await waitFor(() => expect(mocks.getSyncRecording).toHaveBeenCalledWith(SYNC_SESSION_ID));
    expect(mocks.getSyncRecording).not.toHaveBeenCalledWith(TAKE_ID);
  });

  it("falls back to take.source_session_id when no ?session= param", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    await waitFor(() => expect(mocks.getSyncRecording).toHaveBeenCalledWith(SYNC_SESSION_ID));
    expect(mocks.getSyncRecording).not.toHaveBeenCalledWith(TAKE_ID);
  });

  it("allows proceeding when videos are ready even if take status is failed", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    // take 状态为 failed，但双视频已注册 → 素材闸只看视频就绪，不看 take.status
    mocks.getCaptureTake.mockResolvedValue({ ...makeTake(SYNC_SESSION_ID), status: "failed" });
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    const nextButton = await screen.findByRole("button", { name: /下一步/ });
    // 素材闸只看视频就绪：take.status=failed 不阻塞（jest-dom 未注册，用 DOM 属性断言）
    expect((nextButton as HTMLButtonElement).disabled).toBe(false);
  });

  it("keeps the wizard open when going back and restores calibration drafts", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));
    const onNavigate = vi.fn();

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={onNavigate} />);

    fireEvent.click(await screen.findByRole("button", { name: "下一步：A 机位标定" }));
    expect(screen.getByTestId("calibrator-video-a")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "上一步" }));
    expect(screen.getByRole("button", { name: "下一步：A 机位标定" })).toBeTruthy();
    expect(onNavigate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "下一步：A 机位标定" }));
    fireEvent.click(screen.getByRole("button", { name: "完成标定 video-a" }));
    fireEvent.click(screen.getByRole("button", { name: "完成标定 video-b" }));
    fireEvent.click(screen.getByRole("button", { name: "上一步" }));
    expect(screen.getByTestId("draft-count-video-b").textContent).toBe("4");
    fireEvent.click(screen.getByRole("button", { name: "上一步" }));

    expect(screen.getByTestId("draft-count-video-a").textContent).toBe("4");
  });

  it("disables the first next step until both camera videos are ready", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID, { registered_video_ids: { cam_1: "video-a" } }));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    const nextButton = await screen.findByRole("button", { name: /下一步：A 机位标定/ });
    expect((nextButton as HTMLButtonElement).disabled).toBe(true);
  });

  it("uses the recording duration as the default and maximum clip end", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID, { duration_sec: 300 }));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    fireEvent.click(await screen.findByRole("checkbox", { name: "仅分析指定窗口（快速验证短片段）" }));
    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    expect(inputs[0].value).toBe("0");
    expect(inputs[1].value).toBe("300");
    expect(inputs[1].max).toBe("300");
  });

  it.each([
    ["required", false, "需要标注", "开始标注"],
    ["draft", false, "草稿未完成", "继续标注"],
    ["invalidated", false, "确认已失效", "重新标注"],
    ["confirmed", true, "人工锚点已确认", null],
    ["auto_degraded", true, "仅自动估算", null],
    ["not_required", true, "无需人工标注", null],
  ] as const)("renders sync state %s and applies the server gate", async (state, allowed, label, action) => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus({ state, analysis_allowed: allowed, reason_codes: [state] }));
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    const nextButton = await screen.findByRole("button", { name: /下一步：A 机位标定/ });
    expect(screen.getByText(label)).toBeTruthy();
    expect((nextButton as HTMLButtonElement).disabled).toBe(!allowed);
    if (action) expect(screen.getByRole("button", { name: action })).toBeTruthy();
  });

  it("returns to material checks after a sync preflight submit failure and allows retry", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));
    mocks.createMultiviewAnalysisJob.mockRejectedValue(new Error("sync preflight failed"));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "下一步：A 机位标定" }));
    fireEvent.click(screen.getByRole("button", { name: "完成标定 video-a" }));
    fireEvent.click(screen.getByRole("button", { name: "完成标定 video-b" }));
    fireEvent.click(screen.getByRole("button", { name: "完成球网 cam_1" }));
    fireEvent.click(screen.getByRole("button", { name: "完成球网 cam_2" }));
    fireEvent.click(screen.getByRole("button", { name: "开始双摄协同分析" }));

    expect(await screen.findByText("双摄分析启动失败")).toBeTruthy();
    expect(screen.getByRole("button", { name: "下一步：A 机位标定" })).toBeTruthy();
  });

  it("publishes the opt-in Debug Replay flag as an authoritative joint request", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));
    mocks.createMultiviewAnalysisJob.mockResolvedValue({ id: "job-debug" });

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    fireEvent.click(await screen.findByRole("checkbox", { name: "生成 Debug Replay" }));
    fireEvent.click(await screen.findByRole("button", { name: "下一步：A 机位标定" }));
    fireEvent.click(screen.getByRole("button", { name: "完成标定 video-a" }));
    fireEvent.click(screen.getByRole("button", { name: "完成标定 video-b" }));
    fireEvent.click(screen.getByRole("button", { name: "完成球网 cam_1" }));
    fireEvent.click(screen.getByRole("button", { name: "完成球网 cam_2" }));
    fireEvent.click(screen.getByRole("button", { name: "开始双摄协同分析" }));

    await waitFor(() => expect(mocks.createMultiviewAnalysisJob).toHaveBeenCalled());
    const request = mocks.createMultiviewAnalysisJob.mock.calls[0][0];
    expect(request.executionMode).toBe("joint_tracking_v2");
    expect(request.debugTraceEnabled).toBe(true);
  });

  it("navigates to Analysis Progress preserving the library return after creating the parent job", async () => {
    window.history.replaceState(
      {},
      "",
      `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}&return=${encodeURIComponent("/library/sync_recording/sync-1?view=overview")}`,
    );
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));
    mocks.createMultiviewAnalysisJob.mockResolvedValue({ id: "job-parent" });
    const onNavigate = vi.fn();

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={onNavigate} />);

    fireEvent.click(await screen.findByRole("button", { name: "下一步：A 机位标定" }));
    fireEvent.click(screen.getByRole("button", { name: "完成标定 video-a" }));
    fireEvent.click(screen.getByRole("button", { name: "完成标定 video-b" }));
    fireEvent.click(screen.getByRole("button", { name: "完成球网 cam_1" }));
    fireEvent.click(screen.getByRole("button", { name: "完成球网 cam_2" }));
    fireEvent.click(screen.getByRole("button", { name: "开始双摄协同分析" }));

    await waitFor(() => expect(onNavigate).toHaveBeenCalledTimes(1));
    const [path, options] = onNavigate.mock.calls[0];
    expect(path).toContain("/analysis/job-parent");
    expect(path).toContain(encodeURIComponent("/library/sync_recording/sync-1?view=overview"));
    expect(options).toEqual({ replace: true });
  });
});
