/**
 * Library 统一投影层（libraryAdapter）
 *
 * 把后端的三类资产对象（upload video / RecordingSession / SyncRecordingSession）
 * 投影为统一的 `LibraryItemViewModel`，作为用户层主对象（一场比赛/一个训练视频）。
 *
 * 设计原则（design.md D5/D6/D9）：
 * - LibraryItem identity 与 AnalysisJob identity 完全分离：`ref` 稳定，`primaryAnalysisJobId` 可变
 * - 上传视频拥有独立资产生命周期：只读 `GET /api/videos` catalog 枚举，而非从 Job 反推
 * - 三轴生命周期状态：mediaState × availabilityState × analysisState（正交，不合并）
 * - Primary Analysis Selection：双摄 primary 永远取 multiview Parent，A/B 单摄不顶替
 */

import type {
  AnalysisJobSummary,
  RecordingSession,
  SyncRecordingSession,
  VideoMetadata,
  CameraSlotRole,
} from "../types/report";
import {
  listVideosCatalog,
  listRecordings,
  listSyncRecordings,
  listAnalysisJobs,
  getSyncRecording,
  getRecording,
} from "./analysisClient";
import { isAnalysisJobForSyncRecording } from "./dualCameraAnalysisGrouping";

// ── LibraryItemRef：稳定身份 ──
export type LibraryItemKind = "upload" | "recording" | "sync_recording";

export type LibraryItemRef =
  | { kind: "upload"; sourceId: string }
  | { kind: "recording"; sourceId: string }
  | { kind: "sync_recording"; sourceId: string };

// ── 三轴状态 ──
export type LibraryMediaState = "recording" | "processing" | "ready" | "failed" | "canceled";
export type LibraryAvailabilityState = "available" | "pending" | "unavailable";
export type LibraryAnalysisState =
  | "not_started"
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "canceled";

// 用户需要采取的动作槽（避免 UI 显示「处理中」实则在等用户点按钮）
export type LibraryRequiredAction = "merge" | "retry_merge" | "start_analysis";

export interface LibraryItemViewModel {
  ref: LibraryItemRef;
  title: string;
  sourceType: LibraryItemKind;

  mediaState: LibraryMediaState;
  availabilityState: LibraryAvailabilityState;
  analysisState: LibraryAnalysisState;
  requiredAction?: LibraryRequiredAction;

  /** primary 分析结果（D9 契约选择）；与 ref 解耦，重跑分析不影响 identity */
  primaryAnalysisJobId?: string;
  analysisHistoryCount: number;

  thumbnailUrl?: string;
  previewUrl?: string;

  matchFormat?: "singles" | "doubles";
  cameraSetup?: "single" | "dual";
  startedAt?: string;
  durationSec?: number;
  venue?: string;
  courtName?: string;

  // 来源引用（供工程层 / 详情地址）
  fieldSessionId?: string;
  captureTakeId?: string;
}

// ── Primary Analysis Selection（D9） ──
function isInternalChild(job: AnalysisJobSummary): boolean {
  return job.visibility === "internal";
}

function pickPrimarySyncJob(jobs: AnalysisJobSummary[]): AnalysisJobSummary | undefined {
  // 优先 multiview Parent，内部 child 排除，A/B 单摄不作为 primary
  const candidates = jobs.filter((job) => job.analysisKind === "multiview" && !isInternalChild(job));
  if (candidates.length) {
    return newestFirst(candidates)[0];
  }
  // 无 multiview 时回退到历史 single-view（按上游分组语义仍排除 internal child）
  return newestFirst(candidates)[0];
}

function newestFirst(jobs: AnalysisJobSummary[]): AnalysisJobSummary[] {
  return [...jobs].sort((a, b) => {
    const tA = Date.parse(a.updatedAt) || Date.parse(a.createdAt) || 0;
    const tB = Date.parse(b.updatedAt) || Date.parse(b.createdAt) || 0;
    return tB - tA;
  });
}

// ── 状态映射（source-specific，design.md D6） ──
function mapMediaAndRequired(
  source: "upload" | "recording" | "sync_recording",
  session: SyncRecordingSession | RecordingSession | undefined,
): { mediaState: LibraryMediaState; requiredAction?: LibraryRequiredAction } {
  if (!session) return { mediaState: "ready" };
  if (source === "sync_recording") {
    const sync = session as SyncRecordingSession;
    if (sync.status === "recording") return { mediaState: "recording" };
    if (sync.status === "canceled") return { mediaState: "canceled" };
    if (sync.status === "failed") return { mediaState: "failed" };
    // 合并状态：pending 可能是「等用户点击合并」
    if (sync.merge_status === "pending") {
      return { mediaState: "processing", requiredAction: "merge" };
    }
    if (sync.merge_status === "running") {
      return { mediaState: "processing" };
    }
    if (sync.merge_status === "failed") {
      return { mediaState: "failed", requiredAction: "retry_merge" };
    }
    // completed + merged → 可播放
    return { mediaState: "ready" };
  }
  // recording：status 直接映射
  const rec = session as RecordingSession;
  if (rec.status === "recording") return { mediaState: "recording" };
  if (rec.status === "canceled") return { mediaState: "canceled" };
  if (rec.status === "failed") return { mediaState: "failed" };
  return { mediaState: "ready" };
}

function mapAvailability(
  session: SyncRecordingSession | RecordingSession | undefined,
): LibraryAvailabilityState {
  if (!session) return "available";
  if ("video_availability" in session && session.video_availability) {
    const states = Object.values(session.video_availability as Record<CameraSlotRole, string | undefined>);
    if (states.includes("unavailable")) return "unavailable";
    if (states.includes("pending")) return "pending";
  }
  return "available";
}

function mapAnalysisState(jobs: AnalysisJobSummary[], primary?: AnalysisJobSummary): LibraryAnalysisState {
  if (!primary) return "not_started";
  switch (primary.status) {
    case "queued":
    case "uploaded":
      return "queued";
    case "processing":
      return "running";
    case "completed":
      return "succeeded";
    case "failed":
      return "failed";
    case "canceled":
      return "canceled";
    default:
      return jobs.some(isActiveJob) ? "running" : "not_started";
  }
}

function isActiveJob(job: AnalysisJobSummary): boolean {
  return job.status === "queued" || job.status === "uploaded" || job.status === "processing";
}

// ── 归属判定 ──
function jobBelongsToRecording(job: AnalysisJobSummary, rec: RecordingSession): boolean {
  const sessionId = job.recordingSessionId ?? job.metadata?.recording_session_id;
  if (sessionId && sessionId === rec.session_id) return true;
  return Boolean(
    rec.capture_take_id && job.metadata?.capture_take_id && job.metadata.capture_take_id === rec.capture_take_id,
  );
}

function jobBelongsToVideo(job: AnalysisJobSummary, video: VideoMetadata): boolean {
  // 仅当 job 未归属到任何 recording / sync 时，才视为 upload 拥有
  return Boolean(job.videoId && job.videoId === video.id);
}

// ── 组装器 ──
export interface BuildLibraryOptions {
  jobs?: AnalysisJobSummary[];
  videos?: VideoMetadata[];
  recordings?: RecordingSession[];
  syncRecordings?: SyncRecordingSession[];
}

/** 逐个容错拉取：单一来源失败（如：后端旧进程无 GET /api/videos）不拖垮整个 Library 构建。 */
async function safeList<T>(fetch: () => Promise<T[]>): Promise<T[]> {
  try {
    return await fetch();
  } catch (error) {
    console.warn("[library] 素材来源拉取失败，已降级为空列表", error);
    return [];
  }
}

export async function buildLibraryItems(
  options: BuildLibraryOptions = {},
): Promise<LibraryItemViewModel[]> {
  const [jobs, videos, recordings, syncRecordings] = await Promise.all([
    options.jobs ?? safeList(listAnalysisJobs),
    options.videos ?? safeList(listVideosCatalog),
    options.recordings ?? safeList(listRecordings),
    options.syncRecordings ?? safeList(listSyncRecordings),
  ]);

  const items: LibraryItemViewModel[] = [];

  // 归属到双摄 session 的 job 集合
  const syncRecords = syncRecordings.filter((s) => s.status !== "recording");

  for (const sync of syncRecords) {
    const owned = jobs.filter((job) => isAnalysisJobForSyncRecording(job, sync));
    const primary = pickPrimarySyncJob(owned);
    // 双摄的历史分析 = 公开 multiview Parent 数（A/B 工程单摄不参与 primary/历史主视图）
    const historyCount = owned.filter(
      (j) => j.analysisKind === "multiview" && !isInternalChild(j),
    ).length;
    const { mediaState, requiredAction } = mapMediaAndRequired("sync_recording", sync);
    items.push({
      ref: { kind: "sync_recording", sourceId: sync.session_id },
      title: sync.court_name || `同步录制 · ${sync.session_id}`,
      sourceType: "sync_recording",
      mediaState,
      availabilityState: mapAvailability(sync),
      analysisState: mapAnalysisState(owned, primary),
      requiredAction,
      primaryAnalysisJobId: primary?.id,
      analysisHistoryCount: historyCount,
      cameraSetup: "dual",
      matchFormat: sync.match_format === "doubles" || sync.match_format === "singles" ? sync.match_format : undefined,
      startedAt: sync.started_at,
      durationSec: sync.duration_sec,
      courtName: sync.court_name,
      fieldSessionId: sync.field_session_id,
      captureTakeId: sync.capture_take_id,
    });
  }

  for (const rec of recordings.filter((r) => r.status !== "recording")) {
    const owned = jobs.filter((job) => jobBelongsToRecording(job, rec));
    const primary = newestFirst(owned.filter((j) => !isInternalChild(j)))[0];
    const { mediaState, requiredAction } = mapMediaAndRequired("recording", rec);
    items.push({
      ref: { kind: "recording", sourceId: rec.session_id },
      title: rec.court_name || `录制 · ${rec.session_id}`,
      sourceType: "recording",
      mediaState,
      availabilityState: mapAvailability(rec),
      analysisState: mapAnalysisState(owned, primary),
      requiredAction,
      primaryAnalysisJobId: primary?.id,
      analysisHistoryCount: owned.filter((j) => !isInternalChild(j)).length,
      cameraSetup: "single",
      matchFormat: rec.match_format === "doubles" || rec.match_format === "singles" ? rec.match_format : undefined,
      startedAt: rec.started_at,
      durationSec: rec.duration_sec,
      courtName: rec.court_name,
      fieldSessionId: rec.field_session_id,
      captureTakeId: rec.capture_take_id,
    });
  }

  // upload：来自 video catalog，且其 job 不得属于 recording / sync
  const allSessions = [...syncRecords, ...recordings.filter((r) => r.status !== "recording")];
  for (const video of videos.filter((v) => v.source === "upload" || v.source === undefined)) {
    const owned = jobs.filter(
      (job) => jobBelongsToVideo(job, video)
        && !allSessions.some((s) => "session_id" in s && jobBelongsToRecording(job, s as RecordingSession))
        && !allSessions.some((s) => "session_id" in s && isAnalysisJobForSyncRecording(job, s as SyncRecordingSession)),
    );
    const primary = newestFirst(owned.filter((j) => !isInternalChild(j)))[0];
    items.push({
      ref: { kind: "upload", sourceId: video.id },
      title: video.original_filename.replace(/\.(mp4|mov|m4v)$/i, "") || video.id,
      sourceType: "upload",
      mediaState: "ready",
      availabilityState: "available",
      analysisState: mapAnalysisState(owned, primary),
      requiredAction: !primary ? "start_analysis" : undefined,
      primaryAnalysisJobId: primary?.id,
      analysisHistoryCount: owned.filter((j) => !isInternalChild(j)).length,
      cameraSetup: "single",
      startedAt: video.uploaded_at,
      courtName: undefined,
    });
  }

  return items;
}

/** 从 `LibraryItemRef` 生成稳定 workspace URL 片段（不含 host / query）。 */
export function libraryItemPath(ref: LibraryItemRef): string {
  return `/library/${ref.kind}/${encodeURIComponent(ref.sourceId)}`;
}

/**
 * 按 `LibraryItemRef` 精确解析单个素材（workspace 直查路径）。
 * 不依赖全库 `buildLibraryItems` 聚合；某单一来源缺失/失败不会导致无法定位目标素材。
 */
export async function resolveLibraryItemByRef(ref: LibraryItemRef): Promise<LibraryItemViewModel | null> {
  const jobs = await safeList(listAnalysisJobs);

  if (ref.kind === "sync_recording") {
    const sync = await getSyncRecordingSafe(ref.sourceId);
    if (!sync) return null;
    const owned = jobs.filter((job) => isAnalysisJobForSyncRecording(job, sync));
    const primary = pickPrimarySyncJob(owned);
    const { mediaState, requiredAction } = mapMediaAndRequired("sync_recording", sync);
    return {
      ref,
      title: sync.court_name || `同步录制 · ${sync.session_id}`,
      sourceType: "sync_recording",
      mediaState,
      availabilityState: mapAvailability(sync),
      analysisState: mapAnalysisState(owned, primary),
      requiredAction,
      primaryAnalysisJobId: primary?.id,
      analysisHistoryCount: owned.filter((j) => j.analysisKind === "multiview" && !isInternalChild(j)).length,
      cameraSetup: "dual",
      matchFormat: sync.match_format === "doubles" || sync.match_format === "singles" ? sync.match_format : undefined,
      startedAt: sync.started_at,
      durationSec: sync.duration_sec,
      courtName: sync.court_name,
      fieldSessionId: sync.field_session_id,
      captureTakeId: sync.capture_take_id,
    };
  }

  if (ref.kind === "recording") {
    const rec = await getRecordingSafe(ref.sourceId);
    if (!rec) return null;
    const owned = jobs.filter((job) => jobBelongsToRecording(job, rec));
    const primary = newestFirst(owned.filter((j) => !isInternalChild(j)))[0];
    const { mediaState, requiredAction } = mapMediaAndRequired("recording", rec);
    return {
      ref,
      title: rec.court_name || `录制 · ${rec.session_id}`,
      sourceType: "recording",
      mediaState,
      availabilityState: mapAvailability(rec),
      analysisState: mapAnalysisState(owned, primary),
      requiredAction,
      primaryAnalysisJobId: primary?.id,
      analysisHistoryCount: owned.filter((j) => !isInternalChild(j)).length,
      cameraSetup: "single",
      matchFormat: rec.match_format === "doubles" || rec.match_format === "singles" ? rec.match_format : undefined,
      startedAt: rec.started_at,
      durationSec: rec.duration_sec,
      courtName: rec.court_name,
      fieldSessionId: rec.field_session_id,
      captureTakeId: rec.capture_take_id,
    };
  }

  // upload：从 catalog 中按 id 定位；不依赖从 Job 反推（D5）
  const videos = await safeList(listVideosCatalog);
  const video = videos.find((v) => v.id === ref.sourceId);
  if (!video) return null;
  const allSessions: RecordingSession[] = [];
  const owned = jobs.filter((job) => jobBelongsToVideo(job, video) && !allSessions.some((s) => jobBelongsToRecording(job, s)));
  const primary = newestFirst(owned.filter((j) => !isInternalChild(j)))[0];
  return {
    ref,
    title: video.original_filename.replace(/\.(mp4|mov|m4v)$/i, "") || video.id,
    sourceType: "upload",
    mediaState: "ready",
    availabilityState: "available",
    analysisState: mapAnalysisState(owned, primary),
    requiredAction: !primary ? "start_analysis" : undefined,
    primaryAnalysisJobId: primary?.id,
    analysisHistoryCount: owned.filter((j) => !isInternalChild(j)).length,
    cameraSetup: "single",
    startedAt: video.uploaded_at,
  };
}

async function getSyncRecordingSafe(sessionId: string): Promise<SyncRecordingSession | null> {
  try {
    return await getSyncRecording(sessionId);
  } catch {
    return null;
  }
}

async function getRecordingSafe(sessionId: string): Promise<RecordingSession | null> {
  try {
    return await getRecording(sessionId);
  } catch {
    return null;
  }
}