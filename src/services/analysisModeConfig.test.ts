import { afterEach, describe, expect, it } from "vitest";
import { initialModuleDraft, modeTargets, moduleDraftReturn, moduleRequest, readAnalysisMode } from "./analysisModeConfig";
import type { PreparedModuleSources } from "../types/analysisModules";
const prepared: PreparedModuleSources = { source_ids: ["source-1"], reference_view_id: "cam_1", sources: [{ source_id: "source-1", video_id: "video-1", view_id: "cam_1", camera_id: "camera-a", duration_ms: 12500, fps: 30, width: 640, height: 360, timing_authority: "source_pts" }] };
afterEach(() => window.history.replaceState({}, "", "/"));
describe("analysis mode input contracts", () => {
  it("defaults to full and maps only requested targets (dependencies belong to planner)", () => {
    expect(readAnalysisMode()).toBe("full");
    expect(modeTargets("pose", [])).toEqual(["pose.sequence"]);
    expect(modeTargets("custom", ["ball.detect", "player.detect", "ball.detect"])).toEqual(["ball.detect", "player.detect"]);
    expect(moduleRequest("ball", initialModuleDraft(), prepared)).toMatchObject({ window: { start_ms: 0, end_ms: 12500 }, sampling: { stride: 2 }, new_version: false });
  });
  it.each([{ start: -1 }, { start: NaN }, { end: NaN }, { end: 13 }, { end: 0 }, { stride: 0 }, { stride: 1.5 }, { targets: [] }, { targets: ["racket.detect"] }])("rejects invalid input %j", (update) => {
    expect(() => moduleRequest("custom", { ...initialModuleDraft(), ...update }, prepared)).toThrow();
  });
  it("converts fractional seconds and retains authoritative dual context", () => {
    const dual = { ...prepared, sync: { reference_camera: "camera-a" }, source_binding: { take_id: "take-1", sync_revision: 2, provenance_fingerprint: "fp" } };
    expect(moduleRequest("player", { ...initialModuleDraft(), start: 1.234, end: 2.345, failurePolicy: "best_effort" }, dual)).toMatchObject({ window: { start_ms: 1234, end_ms: 2345 }, sync: dual.sync, source_binding: dual.source_binding, failure_policy: "best_effort" });
  });
  it("restores sync return configuration without losing original return", () => {
    window.history.replaceState({}, "", "/capture/take-1/analyze?return=%2Flibrary%2Fsync_recording%2Fsync-1");
    const path = moduleDraftReturn("custom", { ...initialModuleDraft(), targets: ["pose.sequence", "ball.detect"], start: 2, end: 8, stride: 3 });
    window.history.replaceState({}, "", path);
    expect(readAnalysisMode()).toBe("custom");
    expect(initialModuleDraft()).toMatchObject({ targets: ["pose.sequence", "ball.detect"], start: 2, end: 8, stride: 3 });
    expect(new URLSearchParams(window.location.search).get("return")).toBe("/library/sync_recording/sync-1");
  });
});
