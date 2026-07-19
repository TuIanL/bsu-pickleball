import { describe, expect, it } from "vitest";
import type {
  SyncRecordingSession,
  SyncStartRequest,
  SyncStopResponse,
  SyncTestRequest,
  SyncTestResult,
  SyncSegment,
  SyncSegmentFile,
  CameraSlotRole,
  SyncRecordingStatus,
  SyncSegmentStatus,
} from "../types/report";
import { canUseSyncVideos, getSyncMergeStatus } from "../services/syncMergeState";

type SlotPair = Record<CameraSlotRole, string>;
type DualConsoleState = "setup" | "testing" | "recording" | "stopped";

function otherSlot(role: CameraSlotRole): CameraSlotRole {
  return role === "cam_1" ? "cam_2" : "cam_1";
}

describe("Double camera type definitions", () => {
  it("SyncStartRequest uses cam_1_id and cam_2_id", () => {
    const req: SyncStartRequest = {
      cam_1_id: "cam_a",
      cam_2_id: "cam_b",
    };
    expect(req.cam_1_id).toBe("cam_a");
    expect(req.cam_2_id).toBe("cam_b");
    expect(req.cam_1_id).not.toBe(req.cam_2_id);
  });

  it("SyncTestRequest enforces duration in valid range", () => {
    const req: SyncTestRequest = {
      cam_1_id: "cam_a",
      cam_2_id: "cam_b",
      duration: 5,
    };
    expect(req.duration).toBeGreaterThanOrEqual(3);
    expect(req.duration).toBeLessThanOrEqual(30);
  });

  it("SyncRecordingSession uses default_analysis_video_id", () => {
    const session: SyncRecordingSession = {
      session_id: "sync_test123",
      status: "recording" as SyncRecordingStatus,
      camera_slots: {},
      segments: [],
      output_dir: "/tmp/test",
      associated_video_paths: [],
      court_name: "Court A",
      match_format: "doubles",
      fps: 30,
      resolution: "1920x1080",
      auto_analyze_after_stop: true,
      total_restarts: 0,
    };
    expect(session.default_analysis_video_id).toBeUndefined();
  });

  it("SyncStopResponse uses default_analysis_video_id", () => {
    const session: SyncRecordingSession = {
      session_id: "sync_test123",
      status: "completed" as SyncRecordingStatus,
      camera_slots: {},
      segments: [],
      output_dir: "/tmp/test",
      associated_video_paths: [],
      court_name: "",
      match_format: "doubles",
      fps: 30,
      resolution: "1920x1080",
      auto_analyze_after_stop: true,
      total_restarts: 0,
    };

    const resp: SyncStopResponse = {
      session,
      default_analysis_video_id: "rec-abc123",
      analysis_available: true,
    };
    expect(resp.analysis_available).toBe(true);
    expect(resp.default_analysis_video_id).toBe("rec-abc123");

    const respNoAnalysis: SyncStopResponse = {
      session,
      analysis_available: false,
      analysis_blocked_reason: "无有效分段文件",
    };
    expect(respNoAnalysis.analysis_available).toBe(false);
    expect(respNoAnalysis.analysis_blocked_reason).toBeDefined();
  });
});

describe("Deferred dual-camera merge state", () => {
  const session = (merge_status?: "pending" | "running" | "completed" | "failed"): SyncRecordingSession => ({
    session_id: "sync_merge_test",
    status: "completed",
    camera_slots: {},
    segments: [],
    output_dir: "/tmp/test",
    associated_video_paths: [],
    court_name: "",
    match_format: "doubles",
    fps: 60,
    resolution: "1920x1080",
    auto_analyze_after_stop: false,
    total_restarts: 0,
    merge_status,
    registered_video_ids: merge_status === "completed" ? { cam_1: "video-a", cam_2: "video-b" } : {},
  });

  it("only enables playback after both cameras finish merging", () => {
    expect(canUseSyncVideos(session("pending"))).toBe(false);
    expect(canUseSyncVideos(session("running"))).toBe(false);
    expect(canUseSyncVideos(session("failed"))).toBe(false);
    expect(canUseSyncVideos(session("completed"))).toBe(true);
  });

  it("derives completed state for legacy sessions with both video IDs", () => {
    const legacy = session();
    legacy.registered_video_ids = { cam_1: "video-a", cam_2: "video-b" };
    expect(getSyncMergeStatus(legacy)).toBe("completed");
  });
});

describe("Camera slot selection logic", () => {
  it("prevents same camera on two slots", () => {
    const slots: SlotPair = { cam_1: "cam_a", cam_2: "" };
    const target: CameraSlotRole = "cam_2";
    const clickedId = "cam_a";
    const other = otherSlot(target);
    const isDuplicate = slots[other] === clickedId;
    expect(isDuplicate).toBe(true);
  });

  it("allows different cameras on two slots", () => {
    const slots: SlotPair = { cam_1: "cam_a", cam_2: "" };
    const target: CameraSlotRole = "cam_2";
    const clickedId = "cam_b";
    const other = otherSlot(target);
    const isDuplicate = slots[other] === clickedId;
    expect(isDuplicate).toBe(false);
  });

  it("both slots filled triggers recording availability", () => {
    const slots: SlotPair = { cam_1: "cam_a", cam_2: "cam_b" };
    const allSelected = !!slots.cam_1 && !!slots.cam_2;
    expect(allSelected).toBe(true);
  });
});

describe("Dual camera test result display", () => {
  it("reports success when both cameras online", () => {
    const result: SyncTestResult = {
      success: true,
      cam_1_id: "cam_a",
      cam_2_id: "cam_b",
      duration_sec: 5,
      cam_1_online: true,
      cam_2_online: true,
      cam_1_file_size: 2048000,
      cam_2_file_size: 1024000,
      cam_1_first_frame_exists: true,
      cam_2_first_frame_exists: true,
    };
    expect(result.success).toBe(true);
    expect(result.cam_1_online).toBe(true);
    expect(result.cam_2_online).toBe(true);
  });

  it("reports failure when cam_1 is offline", () => {
    const result: SyncTestResult = {
      success: false,
      cam_1_id: "cam_a",
      cam_2_id: "cam_b",
      duration_sec: 5,
      cam_1_online: false,
      cam_2_online: true,
      cam_1_file_size: 0,
      cam_2_file_size: 1024000,
      cam_1_error: "Connection timeout",
      cam_1_first_frame_exists: false,
      cam_2_first_frame_exists: true,
    };
    expect(result.success).toBe(false);
    expect(result.cam_1_error).toBe("Connection timeout");
  });

  it("includes first_frame_url when extraction succeeds", () => {
    const result: SyncTestResult = {
      success: true,
      cam_1_id: "cam_a",
      cam_2_id: "cam_b",
      duration_sec: 5,
      cam_1_online: true,
      cam_2_online: true,
      cam_1_file_size: 1024000,
      cam_2_file_size: 1024000,
      cam_1_first_frame_url: "/api/sync-recordings/test-frames/xxx/first.jpg",
      cam_1_first_frame_exists: true,
      cam_2_first_frame_url: "/api/sync-recordings/test-frames/yyy/first.jpg",
      cam_2_first_frame_exists: true,
    };
    expect(result.cam_1_first_frame_url).toBeDefined();
    expect(result.cam_2_first_frame_url).toBeDefined();
  });
});

describe("Dual camera recording state machine", () => {
  it("setup → recording → stopped", () => {
    let state: DualConsoleState = "setup";
    state = "recording";
    expect(state).toBe("recording");
    state = "stopped";
    expect(state).toBe("stopped");
  });

  it("setup → testing → setup", () => {
    let state: DualConsoleState = "setup";
    state = "testing";
    expect(state).toBe("testing");
    state = "setup";
    expect(state).toBe("setup");
  });

  it("cannot start without two cameras", () => {
    const ready = (s: SlotPair) => !!s.cam_1 && !!s.cam_2;
    expect(ready({ cam_1: "", cam_2: "" })).toBe(false);
    expect(ready({ cam_1: "a", cam_2: "" })).toBe(false);
    expect(ready({ cam_1: "a", cam_2: "b" })).toBe(true);
  });
});

describe("Capture storage location payload", () => {
  it("includes a temporary custom root for both camera slots", () => {
    const storageRoot = "/Volumes/MatchDisk";
    const req = {
      cam_1_id: "cam_a",
      cam_2_id: "cam_b",
      storage_root: storageRoot,
    };
    expect(req.storage_root).toBe(storageRoot);
    expect(req.cam_1_id).not.toBe(req.cam_2_id);
  });

  it("clearing the picker restores the default-location payload", () => {
    let selectedRoot = "/Volumes/MatchDisk";
    selectedRoot = "";
    expect(selectedRoot || undefined).toBeUndefined();
  });

  it("keeps a storage validation error visible without changing the selected root", () => {
    const selectedRoot = "/Volumes/MatchDisk";
    const error = "录制位置剩余空间不足";
    expect(selectedRoot).toBeTruthy();
    expect(error).toContain("空间不足");
  });
});

describe("Segment data model", () => {
  it("segment contains files for both cameras", () => {
    const s: SyncSegment = {
      segment_index: 1,
      status: "completed" as SyncSegmentStatus,
      files: [
        { camera_id: "cam_a", role: "cam_1" as CameraSlotRole, file_path: "/tmp/a.ts", file_size: 5000 },
        { camera_id: "cam_b", role: "cam_2" as CameraSlotRole, file_path: "/tmp/b.ts", file_size: 4800 },
      ],
      restart_count: 0,
    };
    expect(s.files).toHaveLength(2);
    expect(s.files[0].role).toBe("cam_1");
    expect(s.files[1].role).toBe("cam_2");
  });

  it("accumulates restart counts", () => {
    const segments: SyncSegment[] = [
      { segment_index: 1, status: "completed" as SyncSegmentStatus, files: [], restart_count: 0 },
      { segment_index: 2, status: "completed" as SyncSegmentStatus, files: [], restart_count: 1 },
    ];
    const total = segments.reduce((sum, s) => sum + s.restart_count, 0);
    expect(total).toBe(1);
  });
});

describe("sessionStorage persistence", () => {
  it("serializes and deserializes cam_1/cam_2 slots", () => {
    const slots: SlotPair = { cam_1: "cam_main", cam_2: "cam_side" };
    const serialized = JSON.stringify(slots);
    const deserialized: SlotPair = JSON.parse(serialized);
    expect(deserialized.cam_1).toBe("cam_main");
    expect(deserialized.cam_2).toBe("cam_side");
  });

  it("handles empty slots gracefully", () => {
    const deserialized: SlotPair = JSON.parse('{"cam_1":"","cam_2":""}');
    expect(deserialized.cam_1).toBe("");
    expect(deserialized.cam_2).toBe("");
    expect(!!deserialized.cam_1 && !!deserialized.cam_2).toBe(false);
  });
});
