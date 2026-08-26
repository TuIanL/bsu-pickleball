import { describe, expect, it } from "vitest";
import type { LibraryItemViewModel } from "../../services/libraryAdapter";
import type { AnalysisPipelineResult } from "../../types/report";
import {
  computeLibraryViewCapabilities,
  isInvalidViewForItem,
  resolveViewCapability,
} from "./viewCapabilities";

function item(partial: Partial<LibraryItemViewModel>): LibraryItemViewModel {
  return {
    ref: { kind: "sync_recording", sourceId: "sync-1" },
    title: "8月20日 双打",
    sourceType: "sync_recording",
    mediaState: "ready",
    availabilityState: "available",
    analysisState: "succeeded",
    displayState: "completed",
    primaryAnalysisJobId: "mv-1",
    analysisHistoryCount: 1,
    ...partial,
  } as LibraryItemViewModel;
}

describe("LibraryViewCapabilities", () => {
  it("未读取 manifest 时报告保持不可用，避免仅凭 completed Job 开放", () => {
    const caps = computeLibraryViewCapabilities(item({}));
    expect(caps.analysis).toBe("available");
    expect(caps.trajectory).toBe("available");
    expect(caps.report).toBe("unavailable");
    expect(caps.technical).toBe("available");
  });

  it("无分析时结果类 view 不可用，视频仍可用（基于 media availability）", () => {
    const caps = computeLibraryViewCapabilities(item({ primaryAnalysisJobId: undefined, analysisState: "not_started" }));
    expect(caps.analysis).toBe("unavailable");
    expect(caps.report).toBe("unavailable");
    expect(caps.trajectory).toBe("unavailable");
    expect(caps.technical).toBe("unavailable");
    expect(caps.video).toBe("available");
  });

  it("availability=unavailable 时视频 view 不可用且带原因", () => {
    const caps = computeLibraryViewCapabilities(item({ availabilityState: "unavailable" }));
    expect(caps.video).toBe("unavailable");
    expect(caps.reasons?.video).toBe("视频存储暂不可用");
  });

  it("这个 change 的非法 view：upload 不支持 segments（→ replace 到 overview）", () => {
    const upload = item({ ref: { kind: "upload", sourceId: "v-1" }, sourceType: "upload" });
    expect(isInvalidViewForItem(upload, "segments")).toBe(true);
    // resolveViewCapability 对合法 view 返回可用
    const caps = computeLibraryViewCapabilities(upload);
    expect(resolveViewCapability(upload, "segments", caps)).toBe("invalid");
  });

  it("合法但缺产物：无分析时停在原 view 显示缺产物提示，而非静默回落", () => {
    const caps = computeLibraryViewCapabilities(item({ primaryAnalysisJobId: undefined, analysisState: "not_started" }));
    expect(resolveViewCapability(item({ primaryAnalysisJobId: undefined, analysisState: "not_started" }), "trajectory", caps)).toBe("missing");
  });

  it("overview 恒可达", () => {
    const caps = computeLibraryViewCapabilities(item({}));
    expect(resolveViewCapability(item({}), "overview", caps)).toBe("available");
  });

  it("segments 无 take 时不可用；有 take 时可用", () => {
    expect(computeLibraryViewCapabilities(item({ fieldSessionId: undefined, captureTakeId: undefined })).segments).toBe("unavailable");
    expect(computeLibraryViewCapabilities(item({ fieldSessionId: "fs-1", captureTakeId: "take-1" })).segments).toBe("available");
  });

  it("selected completed Job 按自己的 manifest 门控球路与报告，不借用 primary 产物", () => {
    const selected = { id: "old", status: "completed", createdAt: "2026-08-01", analysisKind: "multiview" } as const;
    const manifest = { job_id: "old", metrics: {}, artifacts: {} } as unknown as AnalysisPipelineResult;
    const caps = computeLibraryViewCapabilities(item({}), { job: selected, manifest, manifestState: "loaded" });
    expect(caps.analysis).toBe("available");
    expect(caps.report).toBe("unavailable");
    expect(caps.trajectory).toBe("unavailable");
    expect(caps.reasons?.trajectory).toContain("未生成可用球路");
  });

  it("有效 canonical 场地轨迹可开放报告，即使区域统计尚未生成", () => {
    const job = { id: "complete", status: "completed", createdAt: "2026-08-01", analysisKind: "single_view" } as const;
    const manifest = {
      job_id: "complete",
      status: "completed",
      tracks: [{ track_id: "Player_1", court_point: { x: 10, y: 20 } }],
      metrics: { distances: [], speeds: [], kitchen_dwell: [] },
      artifacts: {},
    } as unknown as AnalysisPipelineResult;
    const caps = computeLibraryViewCapabilities(item({}), { job, manifest, manifestState: "loaded" });
    expect(caps.report).toBe("available");
  });

  it("空轨迹、空运动指标和缺失 structured artifact 时报告置灰", () => {
    const job = { id: "empty", status: "completed", createdAt: "2026-08-01", analysisKind: "single_view" } as const;
    const manifest = {
      job_id: "empty",
      status: "completed",
      tracks: [],
      metrics: { distances: [], speeds: [], kitchen_dwell: [] },
      artifacts: { position_visualizations_status: "no_data" },
    } as unknown as AnalysisPipelineResult;
    const caps = computeLibraryViewCapabilities(item({}), { job, manifest, manifestState: "loaded" });
    expect(caps.report).toBe("unavailable");
    expect(caps.reasons?.report).toContain("没有有效球员轨迹");
  });

  it("selected failed/canceled Job 只开放任务级技术诊断", () => {
    for (const status of ["failed", "canceled"] as const) {
      const caps = computeLibraryViewCapabilities(item({}), {
        job: { id: status, status, createdAt: "2026-08-01", analysisKind: "single_view" },
        manifest: null,
        manifestState: "idle",
      });
      expect(caps.analysis).toBe("unavailable");
      expect(caps.report).toBe("unavailable");
      expect(caps.technical).toBe("available");
    }
  });

  it("selected manifest 加载中呈 loading，加载完成后按 Job 独立恢复", () => {
    const job = { id: "old", status: "completed", createdAt: "2026-08-01", analysisKind: "single_view" } as const;
    expect(computeLibraryViewCapabilities(item({}), { job, manifest: null, manifestState: "loading" }).analysis).toBe("loading");
    const manifest = {
      job_id: "old",
      metrics: {},
      artifacts: { ball_trajectory_url: "/old/ball.json" },
    } as unknown as AnalysisPipelineResult;
    expect(computeLibraryViewCapabilities(item({}), { job, manifest, manifestState: "loaded" }).trajectory).toBe("available");
  });
});
