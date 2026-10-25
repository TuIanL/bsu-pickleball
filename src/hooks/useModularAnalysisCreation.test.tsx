import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModulePlan, PreparedModuleSources } from "../types/analysisModules";
import type { AnalysisUploadMetadata } from "../types/report";
import type { AnalysisCreationMode } from "../services/analysisModeConfig";
const api = vi.hoisted(() => ({ loadModuleCatalog: vi.fn(), prepareModuleModels: vi.fn(), previewModulePlan: vi.fn(), createModuleJob: vi.fn(), listAnalysisJobs: vi.fn() }));
vi.mock("../services/analysisModuleClient", async () => ({ ...await vi.importActual("../services/analysisModuleClient"), ...api }));
vi.mock("../services/analysisClient", async () => ({ ...await vi.importActual("../services/analysisClient"), listAnalysisJobs: api.listAnalysisJobs }));
import { useModularAnalysisCreation } from "./useModularAnalysisCreation";
import { AnalysisApiError } from "../services/analysisClient";
const sources: PreparedModuleSources = { source_ids: ["src"], reference_view_id: "cam_1", sources: [{ source_id: "src", video_id: "video-1", view_id: "cam_1", camera_id: "camera", duration_ms: 60000, fps: 30, width: 640, height: 360, timing_authority: "source_pts" }] };
const plan = { plan_id: "plan", plan_hash: "hash", targets: ["pose.sequence"], nodes: [ { capability_id: "player.detect", implementation: { implementation_id: "player.yolo.v1" } }, { capability_id: "pose.sequence", implementation: { implementation_id: "pose.rtmpose.v1" } } ] } as ModulePlan;
function setup() {
  const prepare = vi.fn().mockResolvedValue(sources), onCreated = vi.fn();
  const hook = renderHook(({ mode, sourceKey }) => useModularAnalysisCreation({ mode, sourceKey, prepare, metadata: {} as AnalysisUploadMetadata, onCreated }), { initialProps: { mode: "pose" as AnalysisCreationMode, sourceKey: "one" } });
  return { ...hook, prepare, onCreated };
}
async function ready(hook: ReturnType<typeof setup>) {
  await waitFor(() => expect(hook.result.current.catalog?.enabled).toBe(true));
  await act(() => hook.result.current.prepareInputs());
  await act(() => hook.result.current.previewPlan());
}
beforeEach(() => {
  vi.resetAllMocks(); window.history.replaceState({}, "", "/");
  api.loadModuleCatalog.mockResolvedValue({ enabled: true, capabilities: ["player.detect", "ball.detect", "pose.sequence"].map((capability_id) => ({ capability_id, status: "implemented", implementations: [] })) });
  api.prepareModuleModels.mockResolvedValue({ "player.yolo.v1": { status: "prepared" }, "pose.rtmpose.v1": { status: "prepared" }, "ball.yolo.v1": { status: "missing" } });
  api.previewModulePlan.mockResolvedValue(plan); api.createModuleJob.mockResolvedValue({ id: "job-1" });
});
afterEach(cleanup);
describe("modular creation state transitions", () => {
  it("accepts pose dependencies despite an unrelated missing ball model, submits preview hash once", async () => {
    const hook = setup(); await ready(hook);
    expect(api.previewModulePlan).toHaveBeenCalledWith(expect.objectContaining({ targets: ["pose.sequence"], window: { start_ms: 0, end_ms: 30000 } }));
    await act(async () => { await Promise.all([hook.result.current.submit(), hook.result.current.submit()]); });
    expect(api.createModuleJob).toHaveBeenCalledTimes(1);
    expect(api.createModuleJob).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ sourceFps: 30 }), "hash");
    expect(hook.onCreated).toHaveBeenCalledWith({ id: "job-1" }, sources);
  });
  it("blocks a missing automatic dependency", async () => {
    api.prepareModuleModels.mockResolvedValue({ "pose.rtmpose.v1": { status: "prepared" } });
    const hook = setup(); await ready(hook);
    expect(hook.result.current.plan).toBeNull(); expect(hook.result.current.error).toContain("player.yolo.v1");
    await act(() => hook.result.current.submit()); expect(api.createModuleJob).not.toHaveBeenCalled();
  });
  it("invalidates a preview when fields, modes or sources change", async () => {
    const hook = setup(); await ready(hook);
    act(() => hook.result.current.updateDraft({ end: 4 }));
    expect(hook.result.current.plan).toBeNull(); await act(() => hook.result.current.submit());
    expect(api.createModuleJob).not.toHaveBeenCalled();
    await act(() => hook.result.current.previewPlan());
    hook.rerender({ mode: "ball", sourceKey: "one" }); expect(hook.result.current.plan).toBeNull();
    hook.rerender({ mode: "ball", sourceKey: "two" }); expect(hook.result.current.prepared).toBeNull();
  });
  it("drops a late preview from the previous mode", async () => {
    const hook = setup(); await waitFor(() => expect(hook.result.current.catalog).not.toBeNull());
    await act(() => hook.result.current.prepareInputs());
    let resolve!: (value: ModulePlan) => void;
    api.previewModulePlan.mockImplementation(() => new Promise<ModulePlan>((done) => { resolve = done; }));
    act(() => { void hook.result.current.previewPlan(); });
    hook.rerender({ mode: "ball", sourceKey: "one" });
    await act(async () => resolve(plan));
    expect(hook.result.current.plan).toBeNull(); expect(hook.result.current.busy).toBe(false);
  });
  it("requires preparation again after a stale preview conflict", async () => {
    const hook = setup(); await ready(hook);
    api.createModuleJob.mockRejectedValue(new AnalysisApiError({ message: "stale", path: "/jobs", url: "/jobs", isNetworkError: false, status: 409, backendDetail: '{"code":"plan_preview_stale"}' }));
    await act(() => hook.result.current.submit());
    expect(hook.result.current.prepared).toBeNull(); expect(hook.result.current.plan).toBeNull();
  });
  it("does not retry an uncertain new-version submission and can recover its job from history", async () => {
    const hook = setup(); await waitFor(() => expect(hook.result.current.catalog).not.toBeNull());
    act(() => hook.result.current.updateDraft({ newVersion: true })); await ready(hook);
    api.createModuleJob.mockRejectedValue(new AnalysisApiError({ message: "offline", path: "/jobs", url: "/jobs", isNetworkError: true }));
    await act(() => hook.result.current.submit()); expect(hook.result.current.uncertain).toBe(true);
    await act(() => hook.result.current.submit()); expect(api.createModuleJob).toHaveBeenCalledTimes(1);
    const job = { id: "saved", analysisEngine: "modular_v1", planHash: "hash" };
    api.listAnalysisJobs.mockResolvedValue([job, { id: "other", planHash: "other" }]);
    await act(() => hook.result.current.checkHistory()); expect(hook.result.current.history).toEqual([job]);
    act(() => hook.result.current.openHistoryJob(hook.result.current.history[0]));
    expect(hook.onCreated).toHaveBeenCalledWith(job, sources);
  });
  it("gates planned targets and runtime-disabled submission", async () => {
    api.loadModuleCatalog.mockResolvedValue({ enabled: false, capabilities: [] });
    const hook = setup(); await waitFor(() => expect(hook.result.current.catalog).not.toBeNull());
    await act(() => hook.result.current.prepareInputs()); await act(() => hook.result.current.previewPlan());
    expect(api.previewModulePlan).not.toHaveBeenCalled(); expect(hook.result.current.targetsAvailable).toBe(false);
  });
});
