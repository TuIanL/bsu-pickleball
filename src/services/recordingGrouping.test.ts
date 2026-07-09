import { describe, expect, it } from "vitest";
import type { FieldSession, RecordingSession } from "../types/report";
import { groupRecordingsByFieldSession } from "./recordingGrouping";

function makeFieldSession(id: string, createdAt: string, title = `FS-${id}`): FieldSession {
  return {
    id,
    title,
    venue: "venue",
    court_name: "court",
    capture_mode: "practice",
    match_format: "doubles",
    camera_setup: "single",
    status: "planned",
    notes: "",
    created_at: createdAt,
    updated_at: createdAt,
  };
}

function makeRecording(id: string, fieldSessionId: string | undefined, startedAt: string): RecordingSession {
  return {
    session_id: id,
    camera_id: "cam-1",
    field_session_id: fieldSessionId,
    court_name: "court",
    match_format: "doubles",
    camera_angle: "high",
    fps: 30,
    resolution: "1920x1080",
    auto_analyze_after_stop: false,
    status: "completed",
    started_at: startedAt,
  };
}

describe("groupRecordingsByFieldSession", () => {
  it("按采集任务正常分组", () => {
    const fsA = makeFieldSession("fs-a", "2026-01-01T00:00:00Z");
    const fsB = makeFieldSession("fs-b", "2026-01-02T00:00:00Z");
    const rec1 = makeRecording("r1", "fs-a", "2026-02-01T00:00:00Z");
    const rec2 = makeRecording("r2", "fs-b", "2026-02-02T00:00:00Z");

    const groups = groupRecordingsByFieldSession([fsA, fsB], [rec1, rec2]);

    expect(groups).toHaveLength(2);
    const groupA = groups.find((g) => g.fieldSession?.id === "fs-a");
    const groupB = groups.find((g) => g.fieldSession?.id === "fs-b");
    expect(groupA?.recordings.map((r) => r.session_id)).toEqual(["r1"]);
    expect(groupB?.recordings.map((r) => r.session_id)).toEqual(["r2"]);
  });

  it("保留空采集任务分组", () => {
    const fsA = makeFieldSession("fs-a", "2026-01-01T00:00:00Z");
    const fsEmpty = makeFieldSession("fs-empty", "2026-01-03T00:00:00Z");
    const rec1 = makeRecording("r1", "fs-a", "2026-02-01T00:00:00Z");

    const groups = groupRecordingsByFieldSession([fsA, fsEmpty], [rec1]);

    expect(groups).toHaveLength(2);
    const emptyGroup = groups.find((g) => g.fieldSession?.id === "fs-empty");
    expect(emptyGroup).toBeDefined();
    expect(emptyGroup?.recordings).toHaveLength(0);
  });

  it("field_session_id 为空的录制归入未归类组", () => {
    const fsA = makeFieldSession("fs-a", "2026-01-01T00:00:00Z");
    const rec1 = makeRecording("r1", "fs-a", "2026-02-01T00:00:00Z");
    const recOrphan = makeRecording("r-orphan", undefined, "2026-02-03T00:00:00Z");

    const groups = groupRecordingsByFieldSession([fsA], [rec1, recOrphan]);

    const uncategorized = groups.find((g) => g.fieldSession === null);
    expect(uncategorized).toBeDefined();
    expect(uncategorized?.recordings.map((r) => r.session_id)).toEqual(["r-orphan"]);
  });

  it("指向已删除采集任务的录制归入未归类组", () => {
    const fsA = makeFieldSession("fs-a", "2026-01-01T00:00:00Z");
    const recDeleted = makeRecording("r-deleted", "fs-gone", "2026-02-03T00:00:00Z");

    const groups = groupRecordingsByFieldSession([fsA], [recDeleted]);

    const uncategorized = groups.find((g) => g.fieldSession === null);
    expect(uncategorized).toBeDefined();
    expect(uncategorized?.recordings.map((r) => r.session_id)).toEqual(["r-deleted"]);
  });

  it("组内录制按 started_at 倒序", () => {
    const fsA = makeFieldSession("fs-a", "2026-01-01T00:00:00Z");
    const recOld = makeRecording("r-old", "fs-a", "2026-02-01T00:00:00Z");
    const recNew = makeRecording("r-new", "fs-a", "2026-03-01T00:00:00Z");

    const groups = groupRecordingsByFieldSession([fsA], [recOld, recNew]);

    expect(groups[0].recordings.map((r) => r.session_id)).toEqual(["r-new", "r-old"]);
  });

  it("具名分组按组内最近录制时间倒序，未归类组始终置底", () => {
    const fsOld = makeFieldSession("fs-old", "2026-01-01T00:00:00Z");
    const fsNew = makeFieldSession("fs-new", "2026-01-02T00:00:00Z");
    // fs-old 的录制时间更新，应排在更前
    const recOldFs = makeRecording("r-old-fs", "fs-old", "2026-05-01T00:00:00Z");
    const recNewFs = makeRecording("r-new-fs", "fs-new", "2026-03-01T00:00:00Z");
    const recOrphan = makeRecording("r-orphan", undefined, "2026-06-01T00:00:00Z");

    const groups = groupRecordingsByFieldSession([fsOld, fsNew], [recOldFs, recNewFs, recOrphan]);

    expect(groups[0].fieldSession?.id).toBe("fs-old"); // 最近录制 2026-05 > 2026-03
    expect(groups[1].fieldSession?.id).toBe("fs-new");
    expect(groups[2].fieldSession).toBeNull(); // 未归类置底
  });

  it("空分组按 created_at 倒序参与排序", () => {
    const fsEarly = makeFieldSession("fs-early", "2026-01-01T00:00:00Z");
    const fsLate = makeFieldSession("fs-late", "2026-04-01T00:00:00Z");
    const recEarly = makeRecording("r-early", "fs-early", "2026-02-01T00:00:00Z");

    const groups = groupRecordingsByFieldSession([fsEarly, fsLate], [recEarly]);

    // fs-late 无录制但 created_at 更新，排在有录制的 fs-early 之前
    expect(groups[0].fieldSession?.id).toBe("fs-late");
    expect(groups[1].fieldSession?.id).toBe("fs-early");
  });
});
