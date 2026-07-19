import type { SyncRecordingSession, SyncMergeStatus } from "../types/report";

export function getSyncMergeStatus(session: SyncRecordingSession): SyncMergeStatus {
  if (session.merge_status) return session.merge_status;
  return session.registered_video_ids?.cam_1 && session.registered_video_ids?.cam_2
    ? "completed"
    : "pending";
}

export function canUseSyncVideos(session: SyncRecordingSession): boolean {
  return session.status === "completed"
    && getSyncMergeStatus(session) === "completed"
    && !!session.registered_video_ids?.cam_1
    && !!session.registered_video_ids?.cam_2;
}
