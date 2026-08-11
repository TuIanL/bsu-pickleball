/** Session Adapter —— RecordingSession / SyncRecordingSession → UnifiedCaptureSession */
import type { RecordingSession, SyncRecordingSession, CaptureTakeSummary } from "../types/report";
import type { UnifiedCaptureSession, CaptureTrackRuntime, NormalizedCaptureStopResult } from "../types/capture";
import type { CaptureStopResult } from "../types/report";

/** 根据停止结果状态推导最终阶段 */
export function phaseFromStopStatus(
  status: NormalizedCaptureStopResult["status"],
): "completed" | "partial" | "failed" {
  switch (status) {
    case "completed": return "completed";
    case "partial": return "partial";
    default: return "failed";
  }
}

/** 将后端单摄会话适配为统一前端格式 */
export function adaptRecordingSession(s: RecordingSession): UnifiedCaptureSession {
  if (!s.started_at) throw new Error("RecordingSession 缺少 started_at");

  return {
    sourceType: "recording",
    sourceSessionId: s.session_id,
    captureTakeId: s.capture_take_id ?? "",
    mode: "single",
    startedAt: s.started_at,
    fps: s.fps ?? 60,
    status: mapStatus(s.status),
    tracks: s.camera_id ? [{
      slot: "single",
      cameraId: s.camera_id,
      analysisRole: "default",
    }] : [],
    cameraDisplayNames: {},
    autoAnalysisJobId: s.auto_analysis_job_id ?? undefined,
    storageRoot: s.storage_root,
    sessionDir: s.session_dir,
    storageStatus: s.storage_status,
  };
}

/** 将后端双摄同步会话适配为统一前端格式 */
export function adaptSyncRecordingSession(s: SyncRecordingSession): UnifiedCaptureSession {
  if (!s.started_at) throw new Error("SyncRecordingSession 缺少 started_at");

  const tracks: CaptureTrackRuntime[] = [];
  const slots = s.camera_slots ?? {};
  for (const name of ["cam_1", "cam_2"]) {
    const slot = slots[name];
    if (slot) {
      tracks.push({
        slot: name as "cam_1" | "cam_2",
        cameraId: typeof slot === "string" ? slot : (slot.camera_id ?? ""),
        analysisRole: name === "cam_1" ? "default" : "supplementary",
      });
    }
  }

  return {
    sourceType: "sync_recording",
    sourceSessionId: s.session_id,
    captureTakeId: s.capture_take_id ?? "",
    mode: "dual",
    startedAt: s.started_at,
    fps: s.fps ?? 60,
    status: mapStatus(s.status),
    tracks,
    cameraDisplayNames: {},
    storageRoot: s.storage_root,
    sessionDir: s.session_dir,
    storageStatus: s.storage_status,
    displayMode: s.display_mode,
    showcaseRuntimeId: s.showcase_runtime_id,
    };
}

/** 后端状态 → 前端统一状态映射 */
function mapStatus(s: string): UnifiedCaptureSession["status"] {
  const m: Record<string, UnifiedCaptureSession["status"]> = {
    recording: "recording", completed: "completed",
    failed: "failed", canceled: "canceled", starting: "starting",
  };
  return m[s] ?? "recording";
}

/** 将后端 API 返回的停止结果归一化为前端统一格式 */
export function normalizeCaptureStopResult(result: CaptureStopResult): NormalizedCaptureStopResult {
  if (!result.capture_take?.id) {
    return {
      captureTakeId: "",
      fieldSessionId: result.capture_take?.field_session_id ?? "",
      status: "failed",
      tracks: [],
      analysisAvailable: false,
      warnings: ["CaptureStopResult 缺少 capture_take"],
    };
  }

  return {
    captureTakeId: result.capture_take.id,
    fieldSessionId: result.capture_take.field_session_id,
    status: result.capture_take.status ?? "completed",
    tracks: result.tracks.map(t => ({
      trackId: t.track_id,
      slot: t.slot,
      cameraId: t.camera_id,
      analysisRole: t.analysis_role ?? "default",
      status: t.status ?? "completed",
      videoId: t.video_id,
      durationMs: t.duration_ms,
      fragmentCount: t.fragment_count ?? 1,
      restartCount: t.restart_count ?? 0,
    })),
    analysisAvailable: result.analysis_available,
    defaultAnalysisTrackId: result.default_analysis_track_id ?? undefined,
    defaultAnalysisVideoId: result.default_analysis_video_id ?? undefined,
    analysisBlockedReason: result.analysis_blocked_reason ?? undefined,
    warnings: result.warnings ?? [],
  };
}

/** 恢复单摄停止结果（页面刷新后从后端重建） */
export function normalizeRecoveredSingleResult(
  session: RecordingSession,
  take: CaptureTakeSummary,
): NormalizedCaptureStopResult {
  const status = take.status === "partial" ? "partial" : take.status === "completed" ? "completed" : "failed";
  const durationMs = take.duration_ms ?? (session.duration_sec ?? 0) * 1000;
  return {
    captureTakeId: take.id,
    fieldSessionId: session.field_session_id ?? "",
    status,
    tracks: [{
      trackId: session.session_id,
      slot: "single",
      cameraId: session.camera_id,
      analysisRole: "default",
      status: status === "failed" ? "failed" : "completed",
      videoId: session.video_id,
      durationMs,
      fragmentCount: 1,
      restartCount: 0,
    }],
    analysisAvailable: Boolean(session.video_id),
    defaultAnalysisTrackId: session.session_id,
    defaultAnalysisVideoId: session.video_id,
    warnings: [],
  };
}

/** 恢复双摄停止结果（页面刷新后从后端重建） */
export function normalizeRecoveredDualResult(
  session: SyncRecordingSession,
  take: CaptureTakeSummary,
): NormalizedCaptureStopResult {
  const status = take.status === "partial" ? "partial" : take.status === "completed" ? "completed" : "failed";
  const durationMs = take.duration_ms ?? (session.duration_sec ?? 0) * 1000;
  const slots = session.camera_slots ?? {};
  const tracks = Object.entries(slots).map(([slotName, slotInfo]) => {
    const isCam1 = slotName === "cam_1";
    const vid = isCam1
      ? (session.default_analysis_video_id ?? session.registered_video_ids?.cam_1)
      : session.registered_video_ids?.cam_2;
    return {
      trackId: `${session.session_id}_${slotName}`,
      slot: slotName,
      cameraId: typeof slotInfo === "string" ? slotInfo : slotInfo.camera_id,
      analysisRole: (isCam1 ? "default" : "supplementary") as "default" | "supplementary",
      status: vid ? "completed" : "partial",
      videoId: vid,
      durationMs,
      fragmentCount: session.segments?.length ?? 1,
      restartCount: session.total_restarts ?? 0,
    };
  });

  return {
    captureTakeId: take.id,
    fieldSessionId: session.field_session_id ?? "",
    status,
    tracks,
    analysisAvailable: Boolean(session.default_analysis_video_id),
    defaultAnalysisTrackId: tracks.find(t => t.analysisRole === "default")?.trackId,
    defaultAnalysisVideoId: session.default_analysis_video_id,
    warnings: [],
  };
}
