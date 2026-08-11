import { describe, expect, it } from "vitest";
import {
  parseTaskListContext,
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
