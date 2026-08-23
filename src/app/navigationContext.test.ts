import { describe, expect, it } from "vitest";
import {
  appendReturnPath,
  buildAnalysisProgressPath,
  buildSyncCalibrationPath,
  isValidReturnPath,
  parseTaskListContext,
  resolveAnalysisFlowOrigin,
  resolveLibraryRefFromAnalysisJob,
  taskListPath,
  taskListPathForJob,
  withTaskListContext,
} from "./navigationContext";

describe("task navigation context", () => {
  it("parses supported source, session, and camera values", () => {
    expect(parseTaskListContext("?source=sync_recording&session=sync-1&cam=cam_2")).toEqual({
      source: "sync_recording",
      sessionId: "sync-1",
      cameraSlot: "cam_2",
    });
  });

  it("falls back to upload for an unsupported source", () => {
    expect(parseTaskListContext("?source=unexpected&session=sync-1")).toEqual({
      source: "upload",
      sessionId: "sync-1",
    });
  });

  it("creates stable task list paths for each source", () => {
    expect(taskListPath({ source: "sync_recording", sessionId: "sync-1" })).toBe(
      "/analysis/tasks?source=sync_recording&session=sync-1",
    );
    expect(taskListPath({ source: "recorded", sessionId: "rec-1", cameraSlot: "cam_1" })).toBe(
      "/analysis/tasks?source=recorded&session=rec-1&cam=cam_1",
    );
  });

  it("preserves explicit source while adding context to a result route", () => {
    expect(withTaskListContext("/analysis/job-1?source=sync_recording", { source: "sync_recording", sessionId: "sync-1" })).toBe(
      "/analysis/job-1?source=sync_recording&taskSource=sync_recording&taskSession=sync-1",
    );
  });

  it("infers a multiview job as a dual-camera task when no query context exists", () => {
    window.history.replaceState({}, "", "/analysis/job-1");
    expect(taskListPathForJob({ analysisKind: "multiview", recordingSessionId: "sync-1" })).toBe(
      "/analysis/tasks?source=sync_recording&session=sync-1",
    );
  });
});

describe("analysis flow origin (return 即 origin)", () => {
  it("resolves a library return into a library origin", () => {
    expect(resolveAnalysisFlowOrigin("/library/sync_recording/sync-1?view=overview")).toEqual({
      kind: "library",
      itemKind: "sync_recording",
      sourceId: "sync-1",
      returnPath: "/library/sync_recording/sync-1?view=overview",
    });
  });

  it("resolves an encoded library sourceId by decoding it", () => {
    const origin = resolveAnalysisFlowOrigin("/library/upload/video%20one?view=overview");
    expect(origin.kind).toBe("library");
    if (origin.kind === "library") {
      expect(origin.sourceId).toBe("video one");
    }
  });

  it("resolves a capture return into a capture origin", () => {
    expect(resolveAnalysisFlowOrigin("/capture/fs-1")).toEqual({
      kind: "capture",
      returnPath: "/capture/fs-1",
    });
  });

  it("falls back to task-console when return is missing or invalid", () => {
    expect(resolveAnalysisFlowOrigin(undefined, { source: "recorded", sessionId: "rec-1" })).toEqual({
      kind: "task-console",
      taskContext: { source: "recorded", sessionId: "rec-1" },
    });
    expect(resolveAnalysisFlowOrigin("//evil.example/library/upload/x")).toEqual({
      kind: "task-console",
      taskContext: { source: "upload" },
    });
  });
});

describe("parseTaskListContext source normalization", () => {
  it("normalizes legacy recording alias to recorded", () => {
    expect(parseTaskListContext("?source=recording&session=rec-1")).toEqual({
      source: "recorded",
      sessionId: "rec-1",
    });
  });

  it("keeps falling back to upload for unsupported source", () => {
    expect(parseTaskListContext("?source=unexpected&session=sync-1")).toEqual({
      source: "upload",
      sessionId: "sync-1",
    });
  });
});

describe("URL builder and return safety", () => {
  it("validates in-app absolute paths and rejects protocol-relative paths", () => {
    expect(isValidReturnPath("/library/upload/vid-1?view=overview")).toBe(true);
    expect(isValidReturnPath("//evil.example/path")).toBe(false);
    expect(isValidReturnPath("https://evil.example/path")).toBe(false);
  });

  it("appends return while preserving existing query params", () => {
    expect(appendReturnPath("/analysis/job-1?taskSource=recorded", "/library/recording/rec-1?view=overview")).toBe(
      "/analysis/job-1?taskSource=recorded&return=%2Flibrary%2Frecording%2Frec-1%3Fview%3Doverview",
    );
  });

  it("ignores an invalid return path", () => {
    expect(appendReturnPath("/analysis/job-1", "//evil.example")).toBe("/analysis/job-1");
  });

  it("builds an analysis progress path with return", () => {
    expect(buildAnalysisProgressPath("job-1", "/library/upload/vid-1?view=overview")).toBe(
      "/analysis/job-1?return=%2Flibrary%2Fupload%2Fvid-1%3Fview%3Doverview",
    );
  });

  it("builds an analysis progress path with task context and return", () => {
    const path = buildAnalysisProgressPath("job-1", "/library/recording/rec-1?view=overview", {
      source: "recorded",
      sessionId: "rec-1",
    });
    expect(path).toContain("/analysis/job-1?taskSource=recorded&taskSession=rec-1&return=");
    expect(path).toContain(encodeURIComponent("/library/recording/rec-1?view=overview"));
  });

  it("builds a sync calibration path with nested return", () => {
    const path = buildSyncCalibrationPath(
      "take-1",
      "/capture/takes/take-1/analyze?session=sync-1&return=%2Flibrary%2Fsync_recording%2Fsync-1",
    );
    expect(path).toBe(
      "/sync-calibration?take=take-1&return=%2Fcapture%2Ftakes%2Ftake-1%2Fanalyze%3Fsession%3Dsync-1%26return%3D%252Flibrary%252Fsync_recording%252Fsync-1",
    );
  });
});

describe("resolveLibraryRefFromAnalysisJob", () => {
  it("resolves a multiview job to a sync_recording ref", () => {
    expect(resolveLibraryRefFromAnalysisJob({ analysisKind: "multiview", recordingSessionId: "sync-1" })).toEqual({
      kind: "sync_recording",
      sourceId: "sync-1",
    });
  });

  it("resolves a capture-take-derived job to a sync_recording ref via metadata", () => {
    expect(resolveLibraryRefFromAnalysisJob({ metadata: { recording_session_id: "sync-2", capture_take_id: "take-1" } })).toEqual({
      kind: "sync_recording",
      sourceId: "sync-2",
    });
  });

  it("resolves a recording session job to a recording ref", () => {
    expect(resolveLibraryRefFromAnalysisJob({ recordingSessionId: "rec-1" })).toEqual({
      kind: "recording",
      sourceId: "rec-1",
    });
  });

  it("resolves a video-only job to an upload ref", () => {
    expect(resolveLibraryRefFromAnalysisJob({ videoId: "vid-1" })).toEqual({
      kind: "upload",
      sourceId: "vid-1",
    });
  });

  it("returns null when no ownership field is present", () => {
    expect(resolveLibraryRefFromAnalysisJob({})).toBeNull();
    expect(resolveLibraryRefFromAnalysisJob(null)).toBeNull();
  });
});
