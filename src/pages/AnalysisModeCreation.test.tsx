import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ loadModuleCatalog: vi.fn(), prepareModuleModels: vi.fn(), prepareModuleVideo: vi.fn(), prepareModuleTake: vi.fn(), previewModulePlan: vi.fn(), createModuleJob: vi.fn(), uploadVideo: vi.fn(), getCaptureTake: vi.fn(), getSyncRecording: vi.fn(), getMetricCourtSceneDraft: vi.fn(), getSyncAnchorStatus: vi.fn() }));
vi.mock("../services/analysisModuleClient", async () => ({ ...await vi.importActual("../services/analysisModuleClient"), ...api }));
vi.mock("../services/analysisClient", async () => ({ ...await vi.importActual("../services/analysisClient"), ...api, getVideoStreamUrl: (id: string) => `/videos/${id}` }));
vi.mock("../components/platform/CourtCornerCalibrator", () => ({ CourtCornerCalibrator: () => <div>完整分析场地标定</div> }));
import { NewAnalysisPage } from "./NewAnalysisPage";
import { RecordingAnalyzePage } from "./RecordingAnalyzePage";
import { MultiViewAnalysisSetupPage } from "./MultiViewAnalysisSetupPage";
const sources = { source_ids: ["src"], reference_view_id: "cam_1", sources: [{ source_id: "src", video_id: "video-1", view_id: "cam_1", camera_id: "camera-a", duration_ms: 10000, fps: 30, width: 640, height: 360, timing_authority: "source_pts" }] };
const clipWindow = { start_ms: 0, end_ms: 10000 };
const plan = { plan_id: "plan", plan_hash: "hash", targets: ["ball.detect"], requested_window: clipWindow, sampling: { stride: 2, phase: 0 }, failure_policy: "all_targets", cache_hints: {}, nodes: [{ node_key: "ball.detect", capability_id: "ball.detect", implementation: { implementation_id: "ball.yolo.v1", resources: [] }, parameters: {}, effective_window: clipWindow, compute_window: clipWindow, truncated: false }] };
beforeEach(() => {
  vi.resetAllMocks();
  api.loadModuleCatalog.mockResolvedValue({ enabled: true, capabilities: [{ capability_id: "ball.detect", status: "implemented" }] });
  api.prepareModuleVideo.mockResolvedValue(sources); api.prepareModuleTake.mockResolvedValue({ ...sources, recording_session_id: "sync-1", source_binding: { take_id: "take-1", sync_revision: 1, provenance_fingerprint: "fp" } });
  api.prepareModuleModels.mockResolvedValue({ "ball.yolo.v1": { status: "prepared" } }); api.previewModulePlan.mockResolvedValue(plan); api.createModuleJob.mockResolvedValue({ id: "module-1" });
  api.getSyncRecording.mockResolvedValue({ session_id: "sync-1", court_name: "测试球场", registered_video_ids: { cam_1: "video-a", cam_2: "video-b" }, camera_slots: {}, status: "completed", match_format: "doubles", fps: 30 });
  api.getCaptureTake.mockResolvedValue({ id: "take-1", capture_mode: "dual", source_session_id: "sync-1", status: "completed" });
  api.getMetricCourtSceneDraft.mockRejectedValue(new Error("场地草稿缺失")); api.getSyncAnchorStatus.mockResolvedValue({ state: "required", analysis_allowed: false, reason_codes: [] });
});
afterEach(() => { cleanup(); globalThis.window.history.replaceState({}, "", "/"); });
async function create() {
  fireEvent.click(await screen.findByRole("button", { name: /^球检测/ }));
  const prepare = await screen.findByRole("button", { name: "准备视频与模型" });
  await waitFor(() => expect(prepare).toBeEnabled()); fireEvent.click(prepare);
  const preview = screen.getByRole("button", { name: "预览执行计划" });
  await waitFor(() => expect(preview).toBeEnabled()); fireEvent.click(preview);
  expect(await screen.findByRole("heading", { name: "本次执行计划" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "创建专项分析" }));
}
describe("three frontend module entry points", () => {
  it("creates from an existing upload without calibration and returns to its library item", async () => {
    globalThis.window.history.replaceState({}, "", "/upload?videoId=video-1");
    const navigate = vi.fn(); render(<NewAnalysisPage onNavigate={navigate} />);
    await create(); await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(screen.queryByText("完整分析场地标定")).not.toBeInTheDocument();
    expect(api.prepareModuleVideo).toHaveBeenCalledWith("video-1");
    expect(navigate).toHaveBeenCalledWith(expect.stringContaining(encodeURIComponent("/library/upload/video-1?view=overview")), { replace: true });
  });
  it("reuses an uploaded file across repeated preparation", async () => {
    globalThis.window.history.replaceState({}, "", "/upload?analysisMode=ball"); api.uploadVideo.mockResolvedValue({ video: { id: "video-1" } });
    render(<NewAnalysisPage onNavigate={vi.fn()} />);
    const input = document.querySelector('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [new File(["video"], "local.mp4", { type: "video/mp4" })] } });
    const button = screen.getByRole("button", { name: "准备视频与模型" }); await waitFor(() => expect(button).toBeEnabled()); fireEvent.click(button);
    fireEvent.click(await screen.findByRole("button", { name: "重新准备视频与模型" }));
    await waitFor(() => expect(api.prepareModuleVideo).toHaveBeenCalledTimes(2)); expect(api.uploadVideo).toHaveBeenCalledTimes(1);
  });
  it("creates selected B camera even with A missing and keeps recording ownership", async () => {
    globalThis.window.history.replaceState({}, "", "/capture/sync-1/analyze?cam=cam_2&return=%2Flibrary%2Fsync_recording%2Fsync-1");
    api.getSyncRecording.mockResolvedValue({ session_id: "sync-1", registered_video_ids: { cam_2: "video-b" }, camera_slots: {}, status: "completed", match_format: "doubles", fps: 30 });
    const navigate = vi.fn(); render(<RecordingAnalyzePage sessionId="sync-1" cam="cam_2" onNavigate={navigate} />);
    await create(); await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(api.prepareModuleVideo).toHaveBeenCalledWith("video-b", "cam_2");
    expect(api.createModuleJob).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ recording_session_id: "sync-1", camera_slot: "cam_2" }), "hash");
    expect(navigate).toHaveBeenCalledWith(expect.stringContaining(encodeURIComponent("/library/sync_recording/sync-1")), { replace: true });
  });
  it("prepares dual sources through take API, bypasses scene requirements, preserves nested sync return", async () => {
    globalThis.window.history.replaceState({}, "", "/capture/takes/take-1/analyze?session=sync-1&return=%2Flibrary%2Fsync_recording%2Fsync-1");
    const navigate = vi.fn(); render(<MultiViewAnalysisSetupPage captureTakeId="take-1" returnParam="/library/sync_recording/sync-1" onNavigate={navigate} />);
    await create(); await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(api.prepareModuleTake).toHaveBeenCalledWith("take-1"); expect(screen.queryByText("完整分析场地标定")).not.toBeInTheDocument();
    expect(api.createModuleJob).toHaveBeenCalledWith(expect.objectContaining({ source_binding: { take_id: "take-1", sync_revision: 1, provenance_fingerprint: "fp" } }), expect.objectContaining({ capture_take_id: "take-1", recording_session_id: "sync-1" }), "hash");
    fireEvent.click(screen.getByRole("button", { name: "打开同步工作台" }));
    const url = new URL(navigate.mock.calls.at(-1)![0], "http://localhost");
    expect(url.pathname).toBe("/sync-calibration");
    const back = new URL(url.searchParams.get("return")!, "http://localhost");
    expect(back.searchParams.get("analysisMode")).toBe("ball"); expect(back.searchParams.get("return")).toBe("/library/sync_recording/sync-1");
  });
});
