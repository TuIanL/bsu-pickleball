import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

const FOUR_POINTS = [
  { id: "top_left", label: "远端左角", viewX: 10, viewY: 10, x: 10, y: 10 },
  { id: "top_right", label: "远端右角", viewX: 90, viewY: 10, x: 90, y: 10 },
  { id: "bottom_right", label: "近端右角", viewX: 90, viewY: 90, x: 90, y: 90 },
  { id: "bottom_left", label: "近端左角", viewX: 10, viewY: 90, x: 10, y: 90 },
];

const NET_DRAFT = {
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
};

vi.mock("../components/platform/CourtCornerCalibrator", () => ({
  CourtCornerCalibrator: (props: {
    videoId: string;
    initialPoints?: unknown[];
    submitLabel?: string;
    title?: string;
    onComplete: (calibrationId: string, points: unknown[]) => void;
  }) => (
    <div data-testid={`calibrator-${props.videoId}`}>
      <span data-testid={`draft-count-${props.videoId}`}>{props.initialPoints?.length ?? 0}</span>
      <span data-testid={`calibrator-title-${props.videoId}`}>{props.title}</span>
      <button
        onClick={() => props.onComplete(`cal-${props.videoId}`, FOUR_POINTS)}
        type="button"
      >
        {props.submitLabel ?? `完成标定 ${props.videoId}`}
      </button>
    </div>
  ),
}));

// 只替换标注器本体：HOLDOUT_ORDER / estimateNetProfileHeight / NetProfileSettings 与
// 领域层的 buildNetProfile 全部使用真实实现，保证「共享高度 profile」走的是生产代码。
vi.mock("../components/platform/NetProfileCalibrator", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../components/platform/NetProfileCalibrator")>();
  return {
    ...actual,
    NetProfileCalibrator: (props: { viewId: string; onComplete: (draft: unknown) => void }) => (
      <div data-testid={`net-calibrator-${props.viewId}`}>
        <button onClick={() => props.onComplete(NET_DRAFT)} type="button">完成球网 {props.viewId}</button>
      </div>
    ),
  };
});

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

/** 完成「球场标定」阶段的两路，并放行进入球网标定。 */
function completeCourtStep() {
  fireEvent.click(screen.getByRole("button", { name: "确认 A 视角球场四角" }));
  fireEvent.click(screen.getByRole("button", { name: "确认 B 视角球场四角" }));
  fireEvent.click(screen.getByRole("button", { name: "下一步：球网标定" }));
}

/** 完成「球网标定」阶段：两路点位 + 共享高度确认，并放行进入名册与确认。 */
function completeNetStep() {
  fireEvent.click(screen.getByRole("button", { name: "完成球网 cam_1" }));
  fireEvent.click(screen.getByRole("button", { name: "完成球网 cam_2" }));
  fireEvent.click(screen.getByRole("checkbox", { name: /我已确认三个控制点/ }));
  fireEvent.click(screen.getByRole("button", { name: "下一步：名册与确认" }));
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

  it("condenses the wizard to three steps with material checks as a persistent status bar", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    // 步骤指示器只有三项
    for (const label of ["球场标定", "球网标定", "名册与确认"]) {
      expect(await screen.findByText(label)).toBeTruthy();
    }
    // 「素材检查」不再是一个步骤，而是常驻状态条
    expect(screen.queryByText("素材检查")).toBeNull();
    expect(screen.getByTestId("material-status-bar")).toBeTruthy();
    expect(screen.getByText("素材与同步")).toBeTruthy();
    // 两路球场标定同页
    const courtPanel = screen.getByTestId("court-calibration-panel");
    expect(within(courtPanel).getByTestId("calibrator-video-a")).toBeTruthy();
    expect(within(courtPanel).getByTestId("calibrator-video-b")).toBeTruthy();
  });

  it("asks for camera orientation before any calibrator on the court step", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    const orientationHeading = await screen.findByText("机位朝向");
    const courtPanel = screen.getByTestId("court-calibration-panel");
    // 朝向必须排在标定器之前：它决定球网左右端的 canonical 语义
    expect(orientationHeading.compareDocumentPosition(courtPanel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole("radio", { name: "A 机位位于球场 A 端底线" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "A 机位位于球场 B 端底线" })).toBeTruthy();
  });

  it("allows proceeding to the net step when videos are ready even if take status is failed", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    // take 状态为 failed，但双视频已注册 → 素材闸只看视频就绪，不看 take.status
    mocks.getCaptureTake.mockResolvedValue({ ...makeTake(SYNC_SESSION_ID), status: "failed" });
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    const nextButton = await screen.findByRole("button", { name: "下一步：球网标定" });
    // 未完成标定时仍禁用（门控靠两路完成度，而不是 take.status）
    expect((nextButton as HTMLButtonElement).disabled).toBe(true);

    completeCourtStep();

    expect(screen.getByTestId("net-calibration-panel")).toBeTruthy();
  });

  it("disables the first next step until both camera videos are ready", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID, { registered_video_ids: { cam_1: "video-a" } }));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    const nextButton = await screen.findByRole("button", { name: "下一步：球网标定" });
    expect((nextButton as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/双摄素材尚未全部就绪/)).toBeTruthy();
  });

  it("keeps the wizard open when going back and restores both camera drafts", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));
    const onNavigate = vi.fn();

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={onNavigate} />);

    await screen.findByTestId("court-calibration-panel");
    completeCourtStep();
    expect(screen.getByTestId("net-calibration-panel")).toBeTruthy();

    // 回到球场标定：两路草稿都还在，且没有离开向导
    fireEvent.click(screen.getByRole("button", { name: "上一步" }));
    expect(screen.getByTestId("draft-count-video-a").textContent).toBe("4");
    expect(screen.getByTestId("draft-count-video-b").textContent).toBe("4");
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("blocks the step until both sides are done and names the missing side", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: "确认 A 视角球场四角" }));

    const nextButton = screen.getByRole("button", { name: "下一步：球网标定" });
    expect((nextButton as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("尚未完成：B 视角")).toBeTruthy();
    // A 路已提交，B 路仍未动过 → 两侧草稿互不干扰
    expect(screen.getByTestId("draft-count-video-a").textContent).toBe("4");
    expect(screen.getByTestId("draft-count-video-b").textContent).toBe("0");

    fireEvent.click(screen.getByRole("button", { name: "确认 B 视角球场四角" }));
    expect((screen.getByRole("button", { name: "下一步：球网标定" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("clears net drafts when the camera orientation changes", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    await screen.findByTestId("court-calibration-panel");
    completeCourtStep();
    completeNetStep();
    expect(screen.getByText("名册与确认 · 双摄协同分析")).toBeTruthy();

    // 回到球场标定改朝向：球网左右端语义翻转，旧点位作废
    fireEvent.click(screen.getByRole("button", { name: "返回修改朝向" }));
    fireEvent.click(screen.getByRole("radio", { name: "A 机位位于球场 B 端底线" }));
    fireEvent.click(screen.getByRole("button", { name: "下一步：球网标定" }));

    expect(screen.getByText(/此前标注的球网点位已作废/)).toBeTruthy();
    // 球网点位被清空 → 必须重做才能继续
    expect((screen.getByRole("button", { name: "下一步：名册与确认" }) as HTMLButtonElement).disabled).toBe(true);
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

    const statusBar = await screen.findByTestId("material-status-bar");
    expect(within(statusBar).getByText(label)).toBeTruthy();
    expect((screen.getByRole("button", { name: "下一步：球网标定" }) as HTMLButtonElement).disabled).toBe(true);

    if (action) expect(within(statusBar).getByRole("button", { name: action })).toBeTruthy();
    if (allowed) {
      expect(within(statusBar).queryByText("先完成同步锚点前置检查")).toBeNull();
    } else {
      expect(within(statusBar).getByText("先完成同步锚点前置检查")).toBeTruthy();
    }
  });

  it("highlights the status bar in place after a submit failure and allows retry", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));
    mocks.createMultiviewAnalysisJob.mockRejectedValue(new Error("sync preflight failed"));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    await screen.findByTestId("court-calibration-panel");
    completeCourtStep();
    completeNetStep();
    // 旧流程绕过名册门控，专注本用例的失败回退语义
    fireEvent.click(screen.getByRole("button", { name: /旧流程/ }));
    fireEvent.click(screen.getByRole("button", { name: "开始双摄协同分析" }));

    // 失败就地高亮顶部状态条，不再把用户弹回一个已不存在的「素材检查」步骤
    expect(await screen.findByText("双摄分析启动失败")).toBeTruthy();
    expect(screen.getByText(/sync preflight failed/)).toBeTruthy();
    expect(screen.getByTestId("material-status-bar")).toBeTruthy();
    expect(screen.getByText("名册与确认 · 双摄协同分析")).toBeTruthy();
    expect(screen.getByRole("button", { name: "重新检查同步" })).toBeTruthy();
  });

  it("publishes the opt-in Debug Replay flag as an authoritative joint request", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));
    mocks.createMultiviewAnalysisJob.mockResolvedValue({ id: "job-debug" });

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    await screen.findByTestId("court-calibration-panel");
    completeCourtStep();
    completeNetStep();
    // 分析配置（Debug Replay / 分析流程）现在位于名册与确认阶段
    fireEvent.click(screen.getByRole("checkbox", { name: "生成 Debug Replay" }));
    fireEvent.click(screen.getByRole("button", { name: /旧流程/ }));
    fireEvent.click(screen.getByRole("button", { name: "开始双摄协同分析" }));

    await waitFor(() => expect(mocks.createMultiviewAnalysisJob).toHaveBeenCalled());
    const request = mocks.createMultiviewAnalysisJob.mock.calls[0][0];
    expect(request.executionMode).toBe("joint_tracking_v2");
    expect(request.debugTraceEnabled).toBe(true);
  });

  it("publishes the shared net height profile for both views", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID));
    mocks.createMultiviewAnalysisJob.mockResolvedValue({ id: "job-shared-profile" });

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    await screen.findByTestId("court-calibration-panel");
    completeCourtStep();

    // 高度只有一份输入；改它就应当同时作用于两路提交载荷
    const endpointInput = screen.getByLabelText(/两侧高度/);
    fireEvent.change(endpointInput, { target: { value: "100" } });

    fireEvent.click(screen.getByRole("button", { name: "完成球网 cam_1" }));
    fireEvent.click(screen.getByRole("button", { name: "完成球网 cam_2" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /我已确认三个控制点/ }));
    fireEvent.click(screen.getByRole("button", { name: "下一步：名册与确认" }));
    fireEvent.click(screen.getByRole("button", { name: /旧流程/ }));
    fireEvent.click(screen.getByRole("button", { name: "开始双摄协同分析" }));

    await waitFor(() => expect(mocks.saveMetricCourtSceneDraft).toHaveBeenCalled());
    const payload = mocks.saveMetricCourtSceneDraft.mock.calls.at(-1)?.[1] as {
      net_profile: { control_points: Array<{ id: string; world: { z: number }; image_by_view: Record<string, unknown> }> };
      views: Array<{ view_id: string }>;
    };
    const left = payload.net_profile.control_points.find((point) => point.id === "left");
    // 100 cm 经共享 profile 换算为英尺
    expect(left?.world.z).toBeCloseTo(100 / 30.48, 6);
    // 两路各自的 image-space 点位都进入同一份 profile
    expect(Object.keys(left?.image_by_view ?? {}).sort()).toEqual(["cam_1", "cam_2"]);
    expect(payload.views.map((view) => view.view_id).sort()).toEqual(["cam_1", "cam_2"]);
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

    await screen.findByTestId("court-calibration-panel");
    completeCourtStep();
    completeNetStep();
    fireEvent.click(screen.getByRole("button", { name: /旧流程/ }));
    fireEvent.click(screen.getByRole("button", { name: "开始双摄协同分析" }));

    await waitFor(() => expect(onNavigate).toHaveBeenCalledTimes(1));
    const [path, options] = onNavigate.mock.calls[0];
    expect(path).toContain("/analysis/job-parent");
    expect(path).toContain(encodeURIComponent("/library/sync_recording/sync-1?view=overview"));
    expect(options).toEqual({ replace: true });
  });

  it("uses the recording duration as the default and maximum clip end", async () => {
    window.history.replaceState({}, "", `/capture/takes/${TAKE_ID}/analyze?session=${SYNC_SESSION_ID}`);
    mocks.getCaptureTake.mockResolvedValue(makeTake(SYNC_SESSION_ID));
    mocks.getSyncAnchorStatus.mockResolvedValue(makeSyncStatus());
    mocks.getSyncRecording.mockResolvedValue(makeSession(SYNC_SESSION_ID, { duration_sec: 300 }));

    render(<MultiViewAnalysisSetupPage captureTakeId={TAKE_ID} onNavigate={vi.fn()} />);

    await screen.findByTestId("court-calibration-panel");
    completeCourtStep();
    completeNetStep();

    // 分析窗口配置位于名册与确认阶段
    const config = screen.getByTestId("analysis-config");
    fireEvent.click(within(config).getByRole("checkbox", { name: "仅分析指定窗口（快速验证短片段）" }));
    const inputs = within(config).getAllByRole("spinbutton") as HTMLInputElement[];
    expect(inputs[0].value).toBe("0");
    expect(inputs[1].value).toBe("300");
    expect(inputs[1].max).toBe("300");
  });
});
