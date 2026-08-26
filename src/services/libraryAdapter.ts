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
  FieldSession,
} from "../types/report";
import {
  listVideosCatalog,
  listRecordings,
  listSyncRecordings,
  listAnalysisJobs,
  listFieldSessions,
  getFieldSession,
  getSyncRecording,
  getRecording,
  getVideoStreamUrl,
  getVideoPosterUrl,
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
  | "canceled"
  | "interrupted";

// 用户需要采取的动作槽（避免 UI 显示「处理中」实则在等用户点按钮）
export type LibraryRequiredAction = "merge" | "retry_merge" | "start_analysis";

// 用户可读的统一展示状态（派生只读，供筛选/徽章/门控消费，不替代三轴状态真源）
export type LibraryDisplayState =
  | "pending" // 待处理
  | "recording" // 正在录制
  | "pending_merge" // 待合并
  | "analyzing" // 正在分析
  | "completed" // 分析完成
  | "failed" // 失败（视频或分析）
  | "canceled" // 已取消
  | "interrupted"; // Worker 失联

export interface LibraryItemViewModel {
  ref: LibraryItemRef;
  title: string;
  sourceType: LibraryItemKind;

  mediaState: LibraryMediaState;
  availabilityState: LibraryAvailabilityState;
  analysisState: LibraryAnalysisState;
  displayState: LibraryDisplayState;
  requiredAction?: LibraryRequiredAction;

  /** primary 分析结果（D9 契约选择；语义收敛为「最新 completed 权威结果」，见 primaryResultAnalysisJobId） */
  primaryAnalysisJobId?: string;
  /** 最新 completed 的权威结果（驱动结果 view 门控；再次分析期间不被 active 任务顶掉） */
  primaryResultAnalysisJobId?: string;
  /** 最新 active 分析任务（驱动进度展示，不参与结果门控） */
  activeAnalysisJobId?: string;
  /** active 任务真实进度 0-100（来自 AnalysisJobSummary.progress） */
  analysisProgress?: number;
  /** active 任务当前阶段文案 */
  analysisStage?: string;
  analysisHistoryCount: number;
  /** 素材的历史分析任务（公开项，新→旧），供「概览」逐任务删除/取消（保留视频） */
  analysisJobs: LibraryAnalysisJobView[];

  thumbnailUrl?: string;
  previewUrl?: string;
  /** 封面可播放视频流地址（用于 <video> 绘制真实首帧；非图片端点） */
  coverVideoUrl?: string;
  /** 双摄素材的两路机位流地址，供封面左右拼接渲染 */
  cameraCoverSources?: { cam_1?: string; cam_2?: string };

  matchFormat?: "singles" | "doubles";
  cameraSetup?: "single" | "dual";
  startedAt?: string;
  durationSec?: number;
  venue?: string;
  courtName?: string;
  /** 用户自定义显示标题（最高优先级；缺省时回退派生 title） */
  displayTitle?: string;
  /** 用户自定义比赛日期（最高优先级；缺省时回退 startedAt） */
  displayDate?: string;

  // 来源引用（供工程层 / 详情地址）
  fieldSessionId?: string;
  captureTakeId?: string;
  /** 源视频 id（单摄录制分析入口需要；upload 用 ref.sourceId） */
  videoId?: string;
}

/** 素材历史分析任务的轻量视图（仅需渲染与删除/取消所需字段） */
export interface LibraryAnalysisJobView {
  id: string;
  status: AnalysisJobSummary["status"];
  analysisKind?: AnalysisJobSummary["analysisKind"];
  executionMode?: AnalysisJobSummary["executionMode"];
  createdAt: string;
  updatedAt?: string;
  progress?: number;
  stage?: AnalysisJobSummary["stage"];
  stageLabel?: string;
  clipStartMs?: number | null;
  clipEndMs?: number | null;
  analysisMode?: AnalysisJobSummary["analysisMode"];
}

/** 组装公开历史任务（新→旧），排除双摄 internal Source Job */
function toAnalysisJobViews(jobs: AnalysisJobSummary[]): LibraryAnalysisJobView[] {
  return newestFirst(jobs.filter((j) => !isInternalChild(j))).map((j) => ({
    id: j.id,
    status: j.status,
    analysisKind: j.analysisKind,
    executionMode: j.executionMode,
    createdAt: j.createdAt,
    updatedAt: j.updatedAt,
    progress: j.progress,
    stage: j.stage,
    stageLabel: j.stages.find((stage) => stage.status === "active" || stage.status === "failed")?.label,
    clipStartMs: j.clipStartMs,
    clipEndMs: j.clipEndMs,
    analysisMode: j.analysisMode,
  }));
}

// ── Primary Analysis Selection（D9） ──
function isInternalChild(job: AnalysisJobSummary): boolean {
  return job.visibility === "internal";
}

// ── displayState / 语义标题（用户可读派生） ──
function deriveDisplayState(s: {
  mediaState: LibraryMediaState;
  analysisState: LibraryAnalysisState;
  requiredAction?: LibraryRequiredAction;
}): LibraryDisplayState {
  if (s.requiredAction === "merge" || s.requiredAction === "retry_merge") return "pending_merge";
  if (s.mediaState === "recording") return "recording";
  if (s.mediaState === "failed") return "failed";
  if (s.mediaState === "canceled" || s.analysisState === "canceled") return "canceled";
  if (s.analysisState === "interrupted") return "interrupted";
  if (s.analysisState === "failed") return "failed";
  if (s.mediaState === "processing") return "pending";
  if (s.analysisState === "running" || s.analysisState === "queued") return "analyzing";
  if (s.analysisState === "succeeded") return "completed";
  return "pending";
}

function semanticTitle(opts: {
  matchTitle?: string;
  startedAt?: string;
  matchFormat?: "singles" | "doubles";
  fallback: string;
}): string {
  if (opts.matchTitle) return opts.matchTitle;
  // 「时间 + 比赛形式」：如「8月20日 双打」
  const date = opts.startedAt ? (() => {
    const d = new Date(opts.startedAt);
    if (Number.isNaN(d.getTime())) return "";
    return `${d.getMonth() + 1}月${d.getDate()}日`;
  })() : "";
  const form = opts.matchFormat === "doubles" ? "双打" : opts.matchFormat === "singles" ? "单打" : "";
  if (date && form) return `${date} ${form}`;
  if (date) return date;
  return opts.fallback;
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

function isActiveJob(job: AnalysisJobSummary): boolean {
  return job.status === "queued" || job.status === "uploaded" || job.status === "processing";
}

// ── Primary Result / Active 分离选择契约（P1） ──
// primaryResultAnalysisJobId = 最新 completed 权威结果（驱动结果 view 门控，不被 active 顶掉）
// activeAnalysisJobId = 最新 active 任务（驱动进度展示，不参与结果门控）

export interface LibraryAnalysisSelection {
  /** 兼容别名：与 primaryResultAnalysisJobId 同值，迁移期保留 */
  primaryAnalysisJobId?: string;
  primaryResultAnalysisJobId?: string;
  activeAnalysisJobId?: string;
  analysisState: LibraryAnalysisState;
  analysisProgress?: number;
  analysisStage?: string;
}

function selectLibraryAnalysisState(jobs: AnalysisJobSummary[]): LibraryAnalysisSelection {
  const active = newestFirst(jobs.filter((j) => !isInternalChild(j) && isActiveJob(j)))[0];
  const result = newestFirst(jobs.filter((j) => !isInternalChild(j) && j.status === "completed"))[0];
  const interrupted = newestFirst(jobs.filter((j) => !isInternalChild(j) && j.status === "interrupted"))[0];
  const currentStage =
    active?.stages.find((s) => s.status === "active") ?? active?.stages.find((s) => s.status === "failed");

  let analysisState: LibraryAnalysisState;
  if (active) {
    analysisState = active.status === "queued" || active.status === "uploaded" ? "queued" : "running";
  } else if (result) {
    analysisState = "succeeded";
  } else if (jobs.some(isActiveJob)) {
    analysisState = "running";
  } else if (interrupted) {
    analysisState = "interrupted";
  } else if (jobs.some((j) => j.status === "failed")) {
    analysisState = "failed";
  } else if (jobs.some((j) => j.status === "canceled")) {
    analysisState = "canceled";
  } else {
    analysisState = "not_started";
  }

  return {
    primaryAnalysisJobId: result?.id,
    primaryResultAnalysisJobId: result?.id,
    activeAnalysisJobId: active?.id,
    analysisState,
    analysisProgress: active?.progress,
    analysisStage: currentStage?.label ?? active?.stage,
  };
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
  const [jobs, videos, recordings, syncRecordings, fieldSessions] = await Promise.all([
    options.jobs ?? safeList(listAnalysisJobs),
    options.videos ?? safeList(listVideosCatalog),
    options.recordings ?? safeList(listRecordings),
    options.syncRecordings ?? safeList(listSyncRecordings),
    safeList(listFieldSessions),
  ]);
  // P2A：一次批量 join FieldSession（建立 Map），禁止每张卡 N+1 拉取
  const fieldSessionById = new Map<string, FieldSession>();
  for (const fs of fieldSessions) fieldSessionById.set(fs.id, fs);

  const items: LibraryItemViewModel[] = [];

  // 归属到双摄 session 的 job 集合
  const syncRecords = syncRecordings.filter((s) => s.status !== "recording");

  for (const sync of syncRecords) {
    const owned = jobs.filter((job) => isAnalysisJobForSyncRecording(job, sync));
    // 双摄只取公开 multiview Parent（A/B 工程单摄不参与 primary/历史主视图/进度）
    const multiviewParents = owned.filter((j) => j.analysisKind === "multiview" && !isInternalChild(j));
    const titleJob = newestFirst(multiviewParents)[0] ?? newestFirst(owned.filter((j) => !isInternalChild(j)))[0];
    const selection = selectLibraryAnalysisState(multiviewParents);
    const historyCount = multiviewParents.length;
    const { mediaState, requiredAction } = mapMediaAndRequired("sync_recording", sync);
    const fs = sync.field_session_id ? fieldSessionById.get(sync.field_session_id) : undefined;
    items.push({
      ref: { kind: "sync_recording", sourceId: sync.session_id },
      title: semanticTitle({
        matchTitle: titleJob?.metadata?.matchTitle,
        startedAt: sync.started_at,
        matchFormat: sync.match_format === "doubles" || sync.match_format === "singles" ? sync.match_format : undefined,
        fallback: sync.court_name || `同步录制 · ${sync.session_id}`,
      }),
      displayTitle: sync.display_title || undefined,
      displayDate: sync.display_date || undefined,
      sourceType: "sync_recording",
      mediaState,
      availabilityState: mapAvailability(sync),
      analysisState: selection.analysisState,
      displayState: deriveDisplayState({ mediaState, analysisState: selection.analysisState, requiredAction }),
      requiredAction,
      // 双摄封面用可播放视频流（default analysis 优先，其次任一注册机位），让前端 <video> 画出首帧
      coverVideoUrl: getVideoStreamUrl(
        sync.default_analysis_video_id ?? sync.registered_video_ids?.cam_1 ?? sync.registered_video_ids?.cam_2,
      ),
      // 预生成 poster（merged video 帧天然左右拼接），命中时前端直接 <img>，跳过视频流解码
      thumbnailUrl: getVideoPosterUrl(
        sync.default_analysis_video_id ?? sync.registered_video_ids?.cam_1 ?? sync.registered_video_ids?.cam_2,
      ),
      // 双摄封面左右拼接：暴露两路机位流地址（存在才填充，缺失由封面渲染层占位）
      cameraCoverSources: {
        ...(sync.registered_video_ids?.cam_1 ? { cam_1: getVideoStreamUrl(sync.registered_video_ids.cam_1) } : {}),
        ...(sync.registered_video_ids?.cam_2 ? { cam_2: getVideoStreamUrl(sync.registered_video_ids.cam_2) } : {}),
      },
      primaryAnalysisJobId: selection.primaryAnalysisJobId,
      primaryResultAnalysisJobId: selection.primaryResultAnalysisJobId,
      activeAnalysisJobId: selection.activeAnalysisJobId,
      analysisProgress: selection.analysisProgress,
      analysisStage: selection.analysisStage,
      analysisHistoryCount: historyCount,
      analysisJobs: toAnalysisJobViews(owned),
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
    const publicOwned = owned.filter((j) => !isInternalChild(j));
    const titleJob = newestFirst(publicOwned)[0];
    const selection = selectLibraryAnalysisState(owned);
    const { mediaState, requiredAction } = mapMediaAndRequired("recording", rec);
    const fs = rec.field_session_id ? fieldSessionById.get(rec.field_session_id) : undefined;
    items.push({
      ref: { kind: "recording", sourceId: rec.session_id },
      title: semanticTitle({
        matchTitle: titleJob?.metadata?.matchTitle,
        startedAt: rec.started_at,
        matchFormat: rec.match_format === "doubles" || rec.match_format === "singles" ? rec.match_format : undefined,
        fallback: rec.court_name || `录制 · ${rec.session_id}`,
      }),
      displayTitle: rec.display_title || undefined,
      displayDate: rec.display_date || undefined,
      sourceType: "recording",
      mediaState,
      availabilityState: mapAvailability(rec),
      analysisState: selection.analysisState,
      displayState: deriveDisplayState({ mediaState, analysisState: selection.analysisState, requiredAction }),
      requiredAction,
      coverVideoUrl: getVideoStreamUrl(rec.video_id),
      thumbnailUrl: getVideoPosterUrl(rec.video_id),
      primaryAnalysisJobId: selection.primaryAnalysisJobId,
      primaryResultAnalysisJobId: selection.primaryResultAnalysisJobId,
      activeAnalysisJobId: selection.activeAnalysisJobId,
      analysisProgress: selection.analysisProgress,
      analysisStage: selection.analysisStage,
      analysisHistoryCount: publicOwned.length,
      analysisJobs: toAnalysisJobViews(owned),
      cameraSetup: "single",
      matchFormat: rec.match_format === "doubles" || rec.match_format === "singles" ? rec.match_format : undefined,
      startedAt: rec.started_at,
      durationSec: rec.duration_sec,
      courtName: rec.court_name,
      fieldSessionId: rec.field_session_id,
      captureTakeId: rec.capture_take_id,
      videoId: rec.video_id,
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
    const publicOwned = owned.filter((j) => !isInternalChild(j));
    const selection = selectLibraryAnalysisState(owned);
    const requiredAction = !selection.primaryAnalysisJobId && !selection.activeAnalysisJobId ? "start_analysis" : undefined;
    items.push({
      ref: { kind: "upload", sourceId: video.id },
      title: video.original_filename.replace(/\.(mp4|mov|m4v)$/i, "") || video.id,
      displayTitle: video.display_title || undefined,
      displayDate: video.display_date || undefined,
      sourceType: "upload",
      mediaState: "ready",
      availabilityState: "available",
      analysisState: selection.analysisState,
      displayState: deriveDisplayState({ mediaState: "ready", analysisState: selection.analysisState, requiredAction }),
      requiredAction,
      coverVideoUrl: getVideoStreamUrl(video.id),
      thumbnailUrl: getVideoPosterUrl(video.id),
      primaryAnalysisJobId: selection.primaryAnalysisJobId,
      primaryResultAnalysisJobId: selection.primaryResultAnalysisJobId,
      activeAnalysisJobId: selection.activeAnalysisJobId,
      analysisProgress: selection.analysisProgress,
      analysisStage: selection.analysisStage,
      analysisHistoryCount: publicOwned.length,
      analysisJobs: toAnalysisJobViews(owned),
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
    const multiviewParents = owned.filter((j) => j.analysisKind === "multiview" && !isInternalChild(j));
    const titleJob = newestFirst(multiviewParents)[0] ?? newestFirst(owned.filter((j) => !isInternalChild(j)))[0];
    const selection = selectLibraryAnalysisState(multiviewParents);
    const { mediaState, requiredAction } = mapMediaAndRequired("sync_recording", sync);
    const fs = sync.field_session_id ? await getFieldSessionSafe(sync.field_session_id) : undefined;
    return {
      ref,
      title: semanticTitle({
        matchTitle: titleJob?.metadata?.matchTitle,
        startedAt: sync.started_at,
        matchFormat: sync.match_format === "doubles" || sync.match_format === "singles" ? sync.match_format : undefined,
        fallback: sync.court_name || `同步录制 · ${sync.session_id}`,
      }),
      displayTitle: sync.display_title || undefined,
      displayDate: sync.display_date || undefined,
      sourceType: "sync_recording",
      mediaState,
      availabilityState: mapAvailability(sync),
      analysisState: selection.analysisState,
      displayState: deriveDisplayState({ mediaState, analysisState: selection.analysisState, requiredAction }),
      requiredAction,
      // 双摄封面用可播放视频流（default analysis 优先），让前端 <video> 画出首帧
      coverVideoUrl: getVideoStreamUrl(sync.default_analysis_video_id ?? sync.registered_video_ids?.cam_1 ?? sync.registered_video_ids?.cam_2),
      // 预生成 poster（merged video 帧天然左右拼接），命中时前端直接 <img>
      thumbnailUrl: getVideoPosterUrl(sync.default_analysis_video_id ?? sync.registered_video_ids?.cam_1 ?? sync.registered_video_ids?.cam_2),
      // 双摄封面左右拼接：暴露两路机位流地址（存在才填充，缺失由封面渲染层占位）
      cameraCoverSources: {
        ...(sync.registered_video_ids?.cam_1 ? { cam_1: getVideoStreamUrl(sync.registered_video_ids.cam_1) } : {}),
        ...(sync.registered_video_ids?.cam_2 ? { cam_2: getVideoStreamUrl(sync.registered_video_ids.cam_2) } : {}),
      },
      primaryAnalysisJobId: selection.primaryAnalysisJobId,
      primaryResultAnalysisJobId: selection.primaryResultAnalysisJobId,
      activeAnalysisJobId: selection.activeAnalysisJobId,
      analysisProgress: selection.analysisProgress,
      analysisStage: selection.analysisStage,
      analysisHistoryCount: multiviewParents.length,
      analysisJobs: toAnalysisJobViews(owned),
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
    const publicOwned = owned.filter((j) => !isInternalChild(j));
    const titleJob = newestFirst(publicOwned)[0];
    const selection = selectLibraryAnalysisState(owned);
    const { mediaState, requiredAction } = mapMediaAndRequired("recording", rec);
    const fs = rec.field_session_id ? await getFieldSessionSafe(rec.field_session_id) : undefined;
    return {
      ref,
      title: semanticTitle({
        matchTitle: titleJob?.metadata?.matchTitle,
        startedAt: rec.started_at,
        matchFormat: rec.match_format === "doubles" || rec.match_format === "singles" ? rec.match_format : undefined,
        fallback: rec.court_name || `录制 · ${rec.session_id}`,
      }),
      displayTitle: rec.display_title || undefined,
      displayDate: rec.display_date || undefined,
      sourceType: "recording",
      mediaState,
      availabilityState: mapAvailability(rec),
      analysisState: selection.analysisState,
      displayState: deriveDisplayState({ mediaState, analysisState: selection.analysisState, requiredAction }),
      requiredAction,
      coverVideoUrl: getVideoStreamUrl(rec.video_id),
      thumbnailUrl: getVideoPosterUrl(rec.video_id),
      primaryAnalysisJobId: selection.primaryAnalysisJobId,
      primaryResultAnalysisJobId: selection.primaryResultAnalysisJobId,
      activeAnalysisJobId: selection.activeAnalysisJobId,
      analysisProgress: selection.analysisProgress,
      analysisStage: selection.analysisStage,
      analysisHistoryCount: publicOwned.length,
      analysisJobs: toAnalysisJobViews(owned),
      cameraSetup: "single",
      matchFormat: rec.match_format === "doubles" || rec.match_format === "singles" ? rec.match_format : undefined,
      startedAt: rec.started_at,
      durationSec: rec.duration_sec,
      courtName: rec.court_name,
      fieldSessionId: rec.field_session_id,
      captureTakeId: rec.capture_take_id,
      videoId: rec.video_id,
    };
  }

  // upload：从 catalog 中按 id 定位；不依赖从 Job 反推（D5）
  const videos = await safeList(listVideosCatalog);
  const video = videos.find((v) => v.id === ref.sourceId);
  if (!video) return null;
  const allSessions: RecordingSession[] = [];
  const owned = jobs.filter((job) => jobBelongsToVideo(job, video) && !allSessions.some((s) => jobBelongsToRecording(job, s)));
  const publicOwned = owned.filter((j) => !isInternalChild(j));
  const selection = selectLibraryAnalysisState(owned);
  const requiredAction = !selection.primaryAnalysisJobId && !selection.activeAnalysisJobId ? "start_analysis" : undefined;
  return {
    ref,
    title: video.original_filename.replace(/\.(mp4|mov|m4v)$/i, "") || video.id,
    displayTitle: video.display_title || undefined,
    displayDate: video.display_date || undefined,
    sourceType: "upload",
    mediaState: "ready",
    availabilityState: "available",
    analysisState: selection.analysisState,
    displayState: deriveDisplayState({ mediaState: "ready", analysisState: selection.analysisState, requiredAction }),
    requiredAction,
    primaryAnalysisJobId: selection.primaryAnalysisJobId,
    primaryResultAnalysisJobId: selection.primaryResultAnalysisJobId,
    activeAnalysisJobId: selection.activeAnalysisJobId,
    analysisProgress: selection.analysisProgress,
    analysisStage: selection.analysisStage,
    analysisHistoryCount: publicOwned.length,
    analysisJobs: toAnalysisJobViews(owned),
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

async function getFieldSessionSafe(id: string): Promise<FieldSession | null> {
  try {
    return await getFieldSession(id);
  } catch {
    return null;
  }
}
