import { describe, expect, it } from "vitest";
import type { LibraryItemViewModel } from "./libraryAdapter";
import { libraryAnalysisEntryPoints, libraryAnalysisPathFor } from "./libraryAnalysisRouting";

function item(partial: Partial<LibraryItemViewModel>): LibraryItemViewModel {
  return {
    ref: { kind: "upload", sourceId: "video-1" },
    title: "测试素材",
    sourceType: "upload",
    mediaState: "ready",
    availabilityState: "available",
    analysisState: "not_started",
    displayState: "pending",
    analysisHistoryCount: 0,
    ...partial,
  } as LibraryItemViewModel;
}

describe("libraryAnalysisPathFor", () => {
  it("upload 返回预填 videoId 的上传分析入口并带 return", () => {
    const p = libraryAnalysisPathFor(item({ ref: { kind: "upload", sourceId: "video-upload" } }));
    expect(p).toContain("/upload?videoId=video-upload");
    expect(p).toContain("return=");
  });

  it("单摄 recording 有 videoId 时返回预填上传分析入口并携带来源上下文", () => {
    const p = libraryAnalysisPathFor(
      item({
        ref: { kind: "recording", sourceId: "rec-1" },
        videoId: "video-rec",
      }),
    );
    expect(p).toContain("/analysis/new?videoId=video-rec&source=recording&sessionId=rec-1");
    expect(p).toContain("return=");
  });

  it("单摄 recording 缺 videoId 时返回 null（不可分析，不伪造）", () => {
    const p = libraryAnalysisPathFor(item({ ref: { kind: "recording", sourceId: "rec-x" }, videoId: undefined }));
    expect(p).toBeNull();
  });

  it("双摄有 captureTakeId 时主入口为双摄协同创建页", () => {
    const p = libraryAnalysisPathFor(
      item({
        ref: { kind: "sync_recording", sourceId: "sync-1" },
        captureTakeId: "take-9",
        sourceType: "sync_recording",
      }),
    );
    expect(p).toContain("/capture/takes/take-9/analyze?session=sync-1");
    expect(p).toContain("return=");
  });
});

describe("libraryAnalysisEntryPoints", () => {
  it("双摄提供 双摄协同 / A 机位 / B 机位 三个入口", () => {
    const points = libraryAnalysisEntryPoints(
      item({
        ref: { kind: "sync_recording", sourceId: "sync-1" },
        captureTakeId: "take-9",
        sourceType: "sync_recording",
      }),
    );
    expect(points).toHaveLength(3);
    expect(points[0].path).toContain("/capture/takes/take-9/analyze");
    expect(points[1].path).toContain("cam=cam_1");
    expect(points[2].path).toContain("cam=cam_2");
  });

  it("双摄缺 captureTakeId 时仍保留 A/B 单摄入口，主入口为 A 机位", () => {
    const points = libraryAnalysisEntryPoints(
      item({ ref: { kind: "sync_recording", sourceId: "sync-1" }, sourceType: "sync_recording" }),
    );
    expect(points[0].label).toBe("A 机位分析");
    expect(points[0].path).toContain("cam=cam_1");
  });

  it("单摄 recording 缺 videoId 时无任何入口", () => {
    const points = libraryAnalysisEntryPoints(
      item({ ref: { kind: "recording", sourceId: "rec-x" }, videoId: undefined }),
    );
    expect(points).toHaveLength(0);
  });

  it("媒体未就绪（录音中/待合并/存储不可用）时返回空入口，不伪造可用", () => {
    expect(
      libraryAnalysisEntryPoints(item({ ref: { kind: "upload", sourceId: "v" }, mediaState: "recording" })),
    ).toHaveLength(0);
    expect(
      libraryAnalysisEntryPoints(
        item({ ref: { kind: "sync_recording", sourceId: "s" }, captureTakeId: "t", sourceType: "sync_recording", requiredAction: "merge" }),
      ),
    ).toHaveLength(0);
    expect(
      libraryAnalysisEntryPoints(
        item({ ref: { kind: "recording", sourceId: "r" }, videoId: "v", availabilityState: "unavailable" }),
      ),
    ).toHaveLength(0);
  });

  it("已分析素材即使存储/视频流不可用也保留再次分析入口", () => {
    const points = libraryAnalysisEntryPoints(
      item({
        ref: { kind: "sync_recording", sourceId: "sync-1" },
        captureTakeId: "take-9",
        sourceType: "sync_recording",
        availabilityState: "unavailable",
        analysisState: "succeeded",
        primaryAnalysisJobId: "job-1",
      }),
    );
    expect(points.length).toBeGreaterThan(0);
    expect(points[0].path).toContain("/capture/takes/take-9/analyze");
  });
});