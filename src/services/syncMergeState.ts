import type { SyncRecordingSession, SyncMergeStatus } from "../types/report";

export function getSyncMergeStatus(session: SyncRecordingSession): SyncMergeStatus {
  if (session.merge_status) return session.merge_status;
  return session.registered_video_ids?.cam_1 && session.registered_video_ids?.cam_2
    ? "completed"
    : "pending";
}

export function canUseSyncVideos(session: SyncRecordingSession): boolean {
  const availability = session.video_availability;
  const hasExplicitAvailability = !!availability && ("cam_1" in availability || "cam_2" in availability);
  return session.status === "completed"
    && getSyncMergeStatus(session) === "completed"
    && !!session.registered_video_ids?.cam_1
    && !!session.registered_video_ids?.cam_2
    && (!hasExplicitAvailability
      || (availability?.cam_1 === "available" && availability?.cam_2 === "available"));
}
