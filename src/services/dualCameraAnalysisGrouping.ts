import type { AnalysisJobSummary, SyncRecordingSession } from "../types/report";

export type DualCameraTaskSlot = "cam_1" | "cam_2";

export interface DualCameraTaskGroup {
  all: AnalysisJobSummary[];
  current?: AnalysisJobSummary;
  history: AnalysisJobSummary[];
}

export interface DualCameraAnalysisGroups {
  multiview: DualCameraTaskGroup;
  singleView: Record<DualCameraTaskSlot, DualCameraTaskGroup>;
  unassigned: AnalysisJobSummary[];
}

function firstNonEmpty(...values: Array<string | undefined>): string | undefined {
  return values.find((value) => Boolean(value));
}

function timestampFor(job: AnalysisJobSummary): number {
  const raw = firstNonEmpty(job.updatedAt, job.createdAt);
  if (!raw) return 0;
  const timestamp = Date.parse(raw);
  return Number.isFinite(timestamp) ? timestamp : 0;
}

/** Stable newest-first ordering independent of the API response order. */
export function sortDualCameraAnalysisJobs(jobs: AnalysisJobSummary[]): AnalysisJobSummary[] {
  return [...jobs].sort((a, b) => {
    const timeDifference = timestampFor(b) - timestampFor(a);
    if (timeDifference !== 0) return timeDifference;
    return b.id.localeCompare(a.id);
  });
}

function buildTaskGroup(jobs: AnalysisJobSummary[]): DualCameraTaskGroup {
  const sorted = sortDualCameraAnalysisJobs(jobs);
  return {
    all: sorted,
    current: sorted[0],
    history: sorted.slice(1),
  };
}

/**
 * Matches the same ownership keys used by the recording-level delete endpoint.
 * The take id is intentionally a fallback, not a fuzzy video/name match.
 */
export function isAnalysisJobForSyncRecording(
  job: AnalysisJobSummary,
  session: SyncRecordingSession,
): boolean {
  const sessionId = firstNonEmpty(job.recordingSessionId, job.metadata?.recording_session_id);
  if (sessionId === session.session_id) return true;

  return Boolean(
    session.capture_take_id
    && job.metadata?.capture_take_id
    && job.metadata.capture_take_id === session.capture_take_id,
  );
}

export function splitAnalysisJobsBySyncRecordings(
  jobs: AnalysisJobSummary[],
  sessions: SyncRecordingSession[],
): { recordingDerivedJobs: AnalysisJobSummary[]; uploadJobs: AnalysisJobSummary[] } {
  const recordingDerivedJobs: AnalysisJobSummary[] = [];
  const uploadJobs: AnalysisJobSummary[] = [];

  for (const job of jobs) {
    if (sessions.some((session) => isAnalysisJobForSyncRecording(job, session))) {
      recordingDerivedJobs.push(job);
    } else {
      uploadJobs.push(job);
    }
  }

  return { recordingDerivedJobs, uploadJobs };
}

export function getDualCameraTaskSlot(
  job: AnalysisJobSummary,
  session: SyncRecordingSession,
): DualCameraTaskSlot | null {
  const explicitSlot = firstNonEmpty(job.cameraSlot, job.metadata?.camera_slot);
  if (explicitSlot === "cam_1" || explicitSlot === "cam_2") return explicitSlot;

  if (job.videoId && job.videoId === session.registered_video_ids?.cam_1) return "cam_1";
  if (job.videoId && job.videoId === session.registered_video_ids?.cam_2) return "cam_2";
  if (job.videoId && job.videoId === session.default_analysis_video_id) return "cam_1";
  return null;
}

export function groupDualCameraAnalysisJobs(
  jobs: AnalysisJobSummary[],
  session: SyncRecordingSession,
): DualCameraAnalysisGroups {
  const multiview: AnalysisJobSummary[] = [];
  const cam1: AnalysisJobSummary[] = [];
  const cam2: AnalysisJobSummary[] = [];
  const unassigned: AnalysisJobSummary[] = [];

  for (const job of jobs) {
    // Parent classification wins even if legacy payloads carry a camera slot.
    if (job.analysisKind === "multiview") {
      multiview.push(job);
      continue;
    }

    const slot = getDualCameraTaskSlot(job, session);
    if (slot === "cam_1") cam1.push(job);
    else if (slot === "cam_2") cam2.push(job);
    else unassigned.push(job);
  }

  return {
    multiview: buildTaskGroup(multiview),
    singleView: {
      cam_1: buildTaskGroup(cam1),
      cam_2: buildTaskGroup(cam2),
    },
    unassigned: sortDualCameraAnalysisJobs(unassigned),
  };
}
