import { describe, expect, it, vi } from "vitest";
import type { AnalysisJobSummary, RecordingSession, SyncRecordingSession, VideoMetadata } from "../types/report";
import { buildLibraryItems, type LibraryItemRef } from "./libraryAdapter";
import { getVideoStreamUrl } from "./analysisClient";

function meta(partial: Record<string, unknown> = {}): AnalysisJobSummary["metadata"] {
  return {
    fileName: "x.mp4",
    matchTitle: "",
    venue: "",
    matchDate: "",
    matchFormat: "doubles",
    cameraAngle: "baseline",
    athleteLabel: "",
    level: "",
    ...partial,
  };
}

function job(partial: Partial<AnalysisJobSummary>): AnalysisJobSummary {
  return {
    id: "job-1",
    status: "completed",
    stage: "completed",
    progress: 100,
    createdAt: "2026-08-20T00:00:00Z",
    updatedAt: "2026-08-20T10:00:00Z",
    metadata: meta(),
    stages: [],
    analysisKind: "single_view",
    ...partial,
  } as AnalysisJobSummary;
}

function video(partial: Partial<VideoMetadata>): VideoMetadata {
  return {
    id: "video-1",
    original_filename: "北体训练.mp4",
    size_bytes: 1024,
    path: "/tmp/x.mp4",
    uploaded_at: "2026-08-20T09:00:00Z",
    source: "upload",
    ...partial,
  };
}

function recording(partial: Partial<RecordingSession>): RecordingSession {
  return {
    session_id: "rec-1",
    camera_id: "cam1",
    court_name: "北体 3 号场",
    match_format: "doubles",
    camera_angle: "valid",
    fps: 50,
    resolution: "1920x1080",
    auto_analyze_after_stop: false,
    status: "completed",
    started_at: "2026-08-20T08:00:00Z",
    duration_sec: 120,
    ...partial,
  };
}

function sync(partial: Partial<SyncRecordingSession>): SyncRecordingSession {
  return {
    session_id: "sync-1",
    status: "completed",
    camera_slots: {},
    segments: [],
    output_dir: "/tmp/sync",
    associated_video_paths: [],
    court_name: "北体 5 号场",
    match_format: "doubles",
    fps: 50,
    resolution: "1920x1080",
    auto_analyze_after_stop: false,
    total_restarts: 0,
    ...partial,
  };
}

const listAnalysisJobs = vi.fn();

vi.mock("./analysisClient", async () => {
  const actual = await vi.importActual<typeof import("./analysisClient")>("./analysisClient");
  return {
    ...actual,
    listAnalysisJobs: () => listAnalysisJobs(),
    listFieldSessions: () => Promise.resolve([]),
    getFieldSession: () => Promise.reject(new Error("field session not found")),
  };
});

describe("buildLibraryItems", () => {
  it("upload 素材有独立资产生命周期（来自 video catalog，而非 Job 反推）", async () => {
    listAnalysisJobs.mockResolvedValue([]);
    const items = await buildLibraryItems({
      videos: [video({})],
      recordings: [],
      syncRecordings: [],
      jobs: [],
    });
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      ref: { kind: "upload", sourceId: "video-1" },
      sourceType: "upload",
      title: "北体训练",
    });
  });

  it("双摄 primary 永远取 multiview Parent，A/B 单摄不顶替（D9）", async () => {
    const parentNew = job({
      id: "mv-2", analysisKind: "multiview", recordingSessionId: "sync-1",
      updatedAt: "2026-08-20T10:20:00Z", metadata: meta({ recording_session_id: "sync-1" }),
    });
    const parentOld = job({
      id: "mv-1", analysisKind: "multiview", recordingSessionId: "sync-1",
      updatedAt: "2026-08-20T09:00:00Z", metadata: meta({ recording_session_id: "sync-1" }),
    });
    const aSingle = job({
      id: "a-1", analysisKind: "single_view", recordingSessionId: "sync-1", cameraSlot: "cam_1",
      updatedAt: "2026-08-20T10:32:00Z", metadata: meta({ recording_session_id: "sync-1" }), visibility: "public",
    });
    listAnalysisJobs.mockResolvedValue([parentNew, parentOld, aSingle]);
    const items = await buildLibraryItems({
      videos: [], recordings: [],
      syncRecordings: [sync({ capture_take_id: "take-1", merge_status: "completed" })],
      jobs: [parentNew, parentOld, aSingle],
    });
    const item = items.find((i) => i.ref.kind === "sync_recording")!;
    expect(item.primaryAnalysisJobId).toBe("mv-2");
    expect(item.analysisHistoryCount).toBe(2); // 两个 multiview Parent，A 单摄不参与 primary
  });

  it("sync merge pending 映射为 processing + requiredAction=merge", async () => {
    listAnalysisJobs.mockResolvedValue([]);
    const items = await buildLibraryItems({
      videos: [], recordings: [],
      syncRecordings: [sync({ merge_status: "pending" })],
      jobs: [],
    });
    const item = items.find((i) => i.ref.kind === "sync_recording")!;
    expect(item).toMatchObject({ mediaState: "processing", requiredAction: "merge" });
  });

  it("双摄投影暴露两路机位流 cameraCoverSources（缺失省略）", async () => {
    listAnalysisJobs.mockResolvedValue([]);
    const syncs = await buildLibraryItems({
      videos: [], recordings: [],
      syncRecordings: [
        sync({
          session_id: "sync-cab",
          registered_video_ids: { cam_1: "cam1-vid", cam_2: "cam2-vid" },
          default_analysis_video_id: "analysis-vid",
        }),
        sync({
          session_id: "sync-1cam",
          registered_video_ids: { cam_1: "cam1-only" },
        }),
      ],
      jobs: [],
    });
    const twoCam = syncs.find((i) => i.ref.sourceId === "sync-cab")!;
    expect(twoCam.coverVideoUrl).toBe(getVideoStreamUrl("analysis-vid")); // coverVideoUrl 为兼容保留
    expect(twoCam.cameraCoverSources).toEqual({
      cam_1: getVideoStreamUrl("cam1-vid"),
      cam_2: getVideoStreamUrl("cam2-vid"),
    });

    const oneCam = syncs.find((i) => i.ref.sourceId === "sync-1cam")!.cameraCoverSources!;
    expect(oneCam).toEqual({ cam_1: getVideoStreamUrl("cam1-only") });
    expect(oneCam.cam_1).toBe(getVideoStreamUrl("cam1-only"));
    expect(oneCam.cam_2).toBeUndefined();
  });

  it("recording 素材按 recordingSessionId 归属取 primary", async () => {
    const recJob = job({
      id: "r-job", analysisKind: "single_view", recordingSessionId: "rec-1",
      metadata: meta({ recording_session_id: "rec-1" }), status: "processing", progress: 62,
    });
    listAnalysisJobs.mockResolvedValue([recJob]);
    const items = await buildLibraryItems({
      videos: [], recordings: [recording({ session_id: "rec-1" })], syncRecordings: [],
      jobs: [recJob],
    });
    const item = items.find((i) => i.ref.kind === "recording")!;
    expect(item.primaryAnalysisJobId).toBe("r-job");
    expect(item.analysisState).toBe("running");
  });

  it("删除 AnalysisJob 契约：adapter 仅编排删除，不把 Job 生命周期当作 Library 资产生命周期", async () => {
    const uploadItem = await buildLibraryItems({
      videos: [video({})], recordings: [], syncRecordings: [], jobs: [],
    });
    // LibraryItem identity 独立于 Job：即便没有 job，upload 素材仍存在
    const ref: LibraryItemRef = uploadItem[0].ref;
    expect(ref.kind).toBe("upload");
    expect(uploadItem[0].analysisState).toBe("not_started");
  });

  it("sync 无 multiview Parent 时 primary 为 undefined，A/B 单摄 NEVER primary", async () => {
    const aSingle = job({
      id: "a-1", analysisKind: "single_view", recordingSessionId: "sync-1", cameraSlot: "cam_1",
      updatedAt: "2026-08-20T10:32:00Z", metadata: meta({ recording_session_id: "sync-1" }), visibility: "public",
    });
    const bSingle = job({
      id: "b-1", analysisKind: "single_view", recordingSessionId: "sync-1", cameraSlot: "cam_2",
      updatedAt: "2026-08-20T10:33:00Z", metadata: meta({ recording_session_id: "sync-1" }), visibility: "public",
    });
    listAnalysisJobs.mockResolvedValue([aSingle, bSingle]);
    const items = await buildLibraryItems({
      videos: [], recordings: [],
      syncRecordings: [sync({ capture_take_id: "take-1", merge_status: "completed" })],
      jobs: [aSingle, bSingle],
    });
    const item = items.find((i) => i.ref.kind === "sync_recording")!;
    expect(item.primaryAnalysisJobId).toBeUndefined();
    expect(item.analysisState).toBe("not_started");
  });

  it("displayState 派生：无分析 upload=pending；running 任务=analyzing；完成=succeeded→completed；待合并=pending_merge", async () => {
    listAnalysisJobs.mockResolvedValue([]);
    const idle = await buildLibraryItems({ videos: [video({})], recordings: [], syncRecordings: [], jobs: [] });
    expect(idle[0].displayState).toBe("pending");

    const recJob = job({
      id: "r-job", analysisKind: "single_view", recordingSessionId: "rec-1",
      metadata: meta({ recording_session_id: "rec-1" }), status: "processing", progress: 62,
    });
    listAnalysisJobs.mockResolvedValue([recJob]);
    const analyzing = await buildLibraryItems({
      videos: [], recordings: [recording({ session_id: "rec-1" })], syncRecordings: [], jobs: [recJob],
    });
    expect(analyzing.find((i) => i.ref.kind === "recording")?.displayState).toBe("analyzing");

    const doneJob = job({ id: "done", analysisKind: "single_view", recordingSessionId: "rec-1", metadata: meta({ recording_session_id: "rec-1" }), status: "completed" });
    listAnalysisJobs.mockResolvedValue([doneJob]);
    const completed = await buildLibraryItems({
      videos: [], recordings: [recording({ session_id: "rec-1" })], syncRecordings: [], jobs: [doneJob],
    });
    expect(completed.find((i) => i.ref.kind === "recording")?.displayState).toBe("completed");

    listAnalysisJobs.mockResolvedValue([]);
    const pendingMerge = await buildLibraryItems({
      videos: [], recordings: [], syncRecordings: [sync({ merge_status: "pending" })], jobs: [],
    });
    expect(pendingMerge.find((i) => i.ref.kind === "sync_recording")?.displayState).toBe("pending_merge");
  });

  it("语义标题优先取 analysis metadata.matchTitle，其次 court_name 与时间+形式", async () => {
    const titledJob = job({
      id: "t", analysisKind: "single_view", recordingSessionId: "rec-1",
      metadata: meta({ recording_session_id: "rec-1", matchTitle: "北京公开赛 · 男双决赛" }), status: "completed",
    });
    listAnalysisJobs.mockResolvedValue([titledJob]);
    const items = await buildLibraryItems({
      videos: [], recordings: [recording({ session_id: "rec-1", court_name: "北体 3 号场" })], syncRecordings: [], jobs: [titledJob],
    });
    expect(items.find((i) => i.ref.kind === "recording")?.title).toBe("北京公开赛 · 男双决赛");

    listAnalysisJobs.mockResolvedValue([]);
    const untitled = await buildLibraryItems({
      videos: [], recordings: [recording({ session_id: "rec-1", court_name: "北体 3 号场", match_format: "singles", started_at: "2026-08-20T08:00:00Z" }), ],
      syncRecordings: [], jobs: [],
    });
    // matchTitle / FieldSession 标题缺失时，用「时间 + 比赛形式」而非 court_name 当主标题
    expect(untitled.find((i) => i.ref.kind === "recording")?.title).toBe("8月20日 单打");
  });
});