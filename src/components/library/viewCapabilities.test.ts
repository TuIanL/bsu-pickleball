import { describe, expect, it } from "vitest";
import type { LibraryItemViewModel } from "../../services/libraryAdapter";
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
  it("分析成功后 analysis/report/trajectory/technical 可用", () => {
    const caps = computeLibraryViewCapabilities(item({}));
    expect(caps.analysis).toBe("available");
    expect(caps.trajectory).toBe("available");
    expect(caps.report).toBe("available");
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
});