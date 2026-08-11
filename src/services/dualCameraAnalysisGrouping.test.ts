import { describe, expect, it } from "vitest";
import type { AnalysisJobSummary, SyncRecordingSession } from "../types/report";
import {
  getDualCameraTaskSlot,
  groupDualCameraAnalysisJobs,
  isAnalysisJobForSyncRecording,
  splitAnalysisJobsBySyncRecordings,
  sortDualCameraAnalysisJobs,
} from "./dualCameraAnalysisGrouping";

const session: SyncRecordingSession = {
  session_id: "sync-1",
  status: "completed",
  camera_slots: {},
  segments: [],
  output_dir: "/tmp/sync-1",
  associated_video_paths: [],
  court_name: "测试球场",
  match_format: "doubles",
  fps: 60,
  resolution: "1920x1080",
  auto_analyze_after_stop: false,
  total_restarts: 0,
  capture_take_id: "take-1",
  registered_video_ids: { cam_1: "video-a", cam_2: "video-b" },
};

function makeJob(id: string, overrides: Partial<AnalysisJobSummary> = {}): AnalysisJobSummary {
  return {
    id,
    status: "completed",
    stage: "report",
    progress: 100,
    createdAt: "2026-08-10T10:00:00.000Z",
    updatedAt: "2026-08-10T10:00:00.000Z",
    metadata: {
      fileName: `${id}.mp4`,
      matchTitle: "测试比赛",
      venue: "测试球场",
      matchDate: "2026-08-10",
      matchFormat: "doubles",
      cameraAngle: "baseline",
      athleteLabel: "测试运动员",
      level: "测试",
    },
    stages: [],
    ...overrides,
  };
}

describe("dualCameraAnalysisGrouping", () => {
  it("matches a recording by session id or capture take id", () => {
    expect(isAnalysisJobForSyncRecording(makeJob("session", { recordingSessionId: "sync-1" }), session)).toBe(true);
    expect(isAnalysisJobForSyncRecording(makeJob("legacy-session", { metadata: { ...makeJob("m").metadata, recording_session_id: "sync-1" } }), session)).toBe(true);
    expect(isAnalysisJobForSyncRecording(makeJob("take", { metadata: { ...makeJob("m").metadata, capture_take_id: "take-1" } }), session)).toBe(true);
    expect(isAnalysisJobForSyncRecording(makeJob("other", { recordingSessionId: "sync-other" }), session)).toBe(false);
  });

  it("keeps sorting stable when updatedAt is missing or equal", () => {
    const newest = makeJob("newest", { updatedAt: "2026-08-10T12:00:00.000Z" });
    const sameTimeB = makeJob("job-z", { updatedAt: "2026-08-10T11:00:00.000Z" });
    const sameTimeA = makeJob("job-a", { updatedAt: "2026-08-10T11:00:00.000Z" });
    const noUpdatedAt = { ...makeJob("created-fallback"), updatedAt: undefined } as unknown as AnalysisJobSummary;

    expect(sortDualCameraAnalysisJobs([sameTimeA, noUpdatedAt, newest, sameTimeB]).map((job) => job.id)).toEqual([
      "newest",
      "job-z",
      "job-a",
      "created-fallback",
    ]);
  });

  it("classifies Parent before camera slots and preserves history", () => {
    const parentOld = makeJob("parent-old", {
      analysisKind: "multiview",
      cameraSlot: "cam_1",
      updatedAt: "2026-08-10T10:00:00.000Z",
    });
    const parentNew = makeJob("parent-new", {
      analysisKind: "multiview",
      updatedAt: "2026-08-10T11:00:00.000Z",
    });
    const cam1Old = makeJob("cam1-old", { cameraSlot: "cam_1", updatedAt: "2026-08-10T10:00:00.000Z" });
    const cam1New = makeJob("cam1-new", { cameraSlot: "cam_1", updatedAt: "2026-08-10T12:00:00.000Z" });
    const cam2ByVideo = makeJob("cam2-video", { videoId: "video-b", updatedAt: "2026-08-10T09:00:00.000Z" });
    const unknown = makeJob("unknown", { videoId: "video-unknown" });

    const groups = groupDualCameraAnalysisJobs(
      [parentOld, cam1Old, unknown, cam2ByVideo, parentNew, cam1New],
      session,
    );

    expect(groups.multiview.current?.id).toBe("parent-new");
    expect(groups.multiview.history.map((job) => job.id)).toEqual(["parent-old"]);
    expect(groups.singleView.cam_1.current?.id).toBe("cam1-new");
    expect(groups.singleView.cam_1.history.map((job) => job.id)).toEqual(["cam1-old"]);
    expect(groups.singleView.cam_2.current?.id).toBe("cam2-video");
    expect(groups.unassigned.map((job) => job.id)).toEqual(["unknown"]);
    expect(getDualCameraTaskSlot(cam2ByVideo, session)).toBe("cam_2");
  });

  it("keeps capture-take-derived jobs out of the upload list", () => {
    const takeJob = makeJob("take-derived", {
      metadata: { ...makeJob("metadata").metadata, capture_take_id: "take-1" },
    });
    const uploadJob = makeJob("plain-upload");

    const split = splitAnalysisJobsBySyncRecordings([takeJob, uploadJob], [session]);

    expect(split.recordingDerivedJobs.map((job) => job.id)).toEqual(["take-derived"]);
    expect(split.uploadJobs.map((job) => job.id)).toEqual(["plain-upload"]);
  });
});
