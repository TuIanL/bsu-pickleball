import { useCallback, useEffect, useMemo, useState } from "react";
import { Camera, Play, RefreshCw, Trash2, Upload, LayoutDashboard, Video, ArrowRight, ArrowDownUp, ListFilter } from "lucide-react";
import type { NavigateFn, AppPath } from "../app/navigationTypes";
import type { AnalysisJobSummary, RecordingSession, FieldSession, SyncRecordingSession } from "../types/report";
import type { DiagnosticNotice } from "../services/analysisDiagnostics";
import { PageFrame } from "../components/PageFrame";
import { Modal } from "../components/platform/Modal";
import { DiagnosticNoticeCard } from "../components/DiagnosticNoticeCard";
import DeleteToast, { type DeleteToastData } from "../components/platform/DeleteToast";
import { FieldSessionGroupCard } from "../components/platform/FieldSessionGroupCard";
import { groupRecordingsByFieldSession } from "../services/recordingGrouping";
import { getVideoStreamUrl } from "../services/analysisClient";
import { canUseSyncVideos, getSyncMergeStatus } from "../services/syncMergeState";
import {
  listAnalysisJobs,
  deleteAnalysisJob,
  deleteAnalysisJobs,
  cancelAnalysisJob,
  rememberAnalysisJob,
  listRecordings,
  deleteRecording,
  listFieldSessions,
  deleteFieldSession,
  listSyncRecordings,
  mergeSyncRecording,
  deleteSyncRecording,
} from "../services/analysisClient";
import {
  errorToNotice,
  isActiveAnalysisJob,
  isCancelableAnalysisJob,
  isTerminalAnalysisJob,
  sortAnalysisJobs,
  analysisStatusMeta,
  analysisModeLabel,
  formatDateTime,
  ANALYSIS_MODES,
  applyModeSelection,
  modeSelectionState,
} from "../utils/analysisHelpers";
import type { AnalysisSortKey, AnalysisSortDir, AnalysisModeValue } from "../utils/analysisHelpers";
import { AnalysisModeSelectPopover } from "../components/platform/AnalysisModeSelectPopover";
import type { AnalysisModeFilter } from "../components/platform/AnalysisModeSelectPopover";

// 会话级持久化：进入任务详情再返回后保持「按类型筛选」的选择
const MODE_FILTER_SESSION_KEY = "analysis-tasks-mode-filter";
const ANALYSIS_MODE_VALUES = ANALYSIS_MODES as readonly AnalysisModeValue[];

function readPersistedModeFilter(): AnalysisModeFilter {
  if (typeof window === "undefined") return "all";
  try {
    const stored = window.sessionStorage.getItem(MODE_FILTER_SESSION_KEY);
    if (stored && ANALYSIS_MODE_VALUES.includes(stored as AnalysisModeValue)) {
      return stored as AnalysisModeValue;
    }
  } catch {
    // sessionStorage 在隐私模式可能不可用，静默回退到默认
  }
  return "all";
}

export function AnalysisTasksPage({
  onNavigate,
  recentJob,
}: {
  onNavigate: NavigateFn;
  recentJob?: AnalysisJobSummary | null;
}) {
  const [jobs, setJobs] = useState<AnalysisJobSummary[] | null>(null);
  const [loadError, setLoadError] = useState<DiagnosticNotice | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([]);
  const [deleteToast, setDeleteToast] = useState<DeleteToastData | null>(null);
  const [deletingJobIds, setDeletingJobIds] = useState<string[]>([]);
  const [cancelingJobIds, setCancelingJobIds] = useState<string[]>([]);

  // 上传任务列表排序：创建/更新时间 × 新→旧 / 旧→新
  const [sortKey, setSortKey] = useState<AnalysisSortKey>("updatedAt");
  const [sortDir, setSortDir] = useState<AnalysisSortDir>("desc");

  // 「按类型选择」弹层开关（仅上传视频任务 tab）
  const [modeSelectOpen, setModeSelectOpen] = useState(false);
  // 「按类型筛选」：全部或某一分析模式（上传任务 tab 列表过滤）
  // 进入详情页再返回时，从 sessionStorage 恢复，保持筛选上下文
  const [modeFilter, setModeFilter] = useState<AnalysisModeFilter>(readPersistedModeFilter);

  /** 写入 modeFilter 并同步持久化到 sessionStorage（详情页返回时 remount 会读回） */
  const updateModeFilter = (next: AnalysisModeFilter) => {
    setModeFilter(next);
    try {
      window.sessionStorage.setItem(MODE_FILTER_SESSION_KEY, next);
    } catch {
      // 忽略隐私模式/无 sessionStorage 时的写入失败
    }
  };

  // 来源筛选：上传视频 / 录制视频 / 双摄录制
  const [sourceFilter, setSourceFilter] = useState<"upload" | "recorded" | "sync_recording">("upload");
  const [recordings, setRecordings] = useState<RecordingSession[]>([]);
  const [recordingsLoading, setRecordingsLoading] = useState(false);
  const [fieldSessions, setFieldSessions] = useState<FieldSession[]>([]);
  const [selectedRecordingIds, setSelectedRecordingIds] = useState<Set<string>>(() => new Set());
  const [isBatchDeleting, setIsBatchDeleting] = useState(false);

  // ── Field Session 批量删除 ──
  const [selectedFieldSessionIds, setSelectedFieldSessionIds] = useState<Set<string>>(() => new Set());
  const [isFieldSessionBatchDeleting, setIsFieldSessionBatchDeleting] = useState(false);

  // 双摄同步录制
  const [syncRecordings, setSyncRecordings] = useState<SyncRecordingSession[]>([]);
  const [syncRecordingsLoading, setSyncRecordingsLoading] = useState(false);
  const [mergingSyncRecordingIds, setMergingSyncRecordingIds] = useState<Set<string>>(() => new Set());
  const [fieldSessionsLoading, setFieldSessionsLoading] = useState(false);
  const [playingSession, setPlayingSession] = useState<RecordingSession | null>(null);
  const [playingSyncSession, setPlayingSyncSession] = useState<SyncRecordingSession | null>(null);
  const [playbackError, setPlaybackError] = useState(false);
  const [syncPlaybackErrors, setSyncPlaybackErrors] = useState<Record<string, boolean>>({});

  const handlePlaySession = (session: RecordingSession) => { setPlaybackError(false); setPlayingSession(session); };
  const handleClosePlayer = () => { setPlayingSession(null); setPlaybackError(false); };
  const handlePlaySyncSession = (session: SyncRecordingSession) => {
    setSyncPlaybackErrors({});
    setPlayingSyncSession(session);
  };
  const handleCloseSyncPlayer = () => {
    setPlayingSyncSession(null);
    setSyncPlaybackErrors({});
  };

  const handleDeleteFieldSession = async (session: FieldSession) => {
    try {
      await deleteFieldSession(session.id);
      await Promise.all([loadFieldSessions(), loadRecordings()]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "删除失败，请刷新后重试";
      alert(msg);
    }
  };

  // ── 录制视频批量删除 ──
  const handleToggleSelectRecording = (sessionId: string) => {
    setSelectedRecordingIds(prev => {
      const next = new Set(prev);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  };

  const handleSelectAllRecordings = () => {
    const deletableIds = recordings
      .filter(r => r.status !== "recording")
      .map(r => r.session_id);
    if (deletableIds.length > 0 && deletableIds.every(id => selectedRecordingIds.has(id))) {
      setSelectedRecordingIds(new Set());
    } else {
      setSelectedRecordingIds(new Set(deletableIds));
    }
  };

  const handleBatchDeleteRecordings = async () => {
    const ids = [...selectedRecordingIds];
    if (!ids.length || isBatchDeleting) return;
    if (!window.confirm(`确定批量删除 ${ids.length} 个录制记录吗？此操作不可撤销。`)) return;

    setIsBatchDeleting(true);
    setDeleteToast(null);

    const results = await Promise.allSettled(ids.map(id => deleteRecording(id)));
    let deleted = 0, blocked = 0, failed = 0;
    for (const r of results) {
      if (r.status === "fulfilled") {
        if (r.value.status === "deleted") deleted++;
        else if (r.value.status === "blocked") blocked++;
        else failed++;
      } else {
        failed++;
      }
    }

    setDeleteToast(buildDeleteToast(deleted, blocked, failed, 0, "录制"));
    setSelectedRecordingIds(new Set());
    setIsBatchDeleting(false);
    void loadRecordings();
    void loadFieldSessions();
  };

  // ── Field Session 批量删除与清理 ──
  const handleToggleSelectFieldSession = (fsId: string) => {
    setSelectedFieldSessionIds(prev => {
      const next = new Set(prev);
      if (next.has(fsId)) next.delete(fsId);
      else next.add(fsId);
      return next;
    });
  };

  const handleBatchDeleteFieldSessions = async () => {
    const ids = [...selectedFieldSessionIds];
    if (!ids.length || isFieldSessionBatchDeleting) return;
    if (!window.confirm(`确定批量删除 ${ids.length} 个采集任务吗？\n注意：包含录制视频的采集任务将无法删除，请先删除录制。`)) return;

    setIsFieldSessionBatchDeleting(true);
    setDeleteToast(null);

    const results = await Promise.allSettled(ids.map(id => deleteFieldSession(id)));
    let deleted = 0, blocked = 0, failed = 0;
    for (const r of results) {
      if (r.status === "fulfilled") {
        if (r.value.status === "deleted") deleted++;
        else if (r.value.status === "blocked") blocked++;
        else failed++;
      } else failed++;
    }

    setDeleteToast(buildDeleteToast(deleted, blocked, failed, 0, "采集任务"));
    setSelectedFieldSessionIds(new Set());
    setIsFieldSessionBatchDeleting(false);
    void loadFieldSessions();
    void loadRecordings();
  };

  const handleCleanEmptyFieldSessions = async () => {
    const emptyGroups = recordingGroups.filter(g => g.recordings.length === 0 && g.fieldSession);
    if (emptyGroups.length === 0) {
      alert("当前没有空的采集任务");
      return;
    }
    if (!window.confirm(`确定清理 ${emptyGroups.length} 个没有录制视频的采集任务吗？此操作不可撤销。`)) return;

    setIsFieldSessionBatchDeleting(true);
    setDeleteToast(null);

    const results = await Promise.allSettled(emptyGroups.map(g => deleteFieldSession(g.fieldSession!.id)));
    let deleted = 0, blocked = 0, failed = 0;
    for (const r of results) {
      if (r.status === "fulfilled") {
        if (r.value.status === "deleted") deleted++;
        else if (r.value.status === "blocked") blocked++;
        else failed++;
      } else failed++;
    }

    setDeleteToast(buildDeleteToast(deleted, blocked, failed, 0, "采集任务"));
    setIsFieldSessionBatchDeleting(false);
    void loadFieldSessions();
    void loadRecordings();
  };

  const loadRecordings = useCallback(async () => {
    setRecordingsLoading(true);
    try {
      setRecordings(await listRecordings());
    } catch {
      setRecordings([]);
    } finally {
      setRecordingsLoading(false);
    }
  }, []);

  const loadFieldSessions = useCallback(async () => {
    setFieldSessionsLoading(true);
    try {
      setFieldSessions(await listFieldSessions());
    } catch {
      setFieldSessions([]);
    } finally {
      setFieldSessionsLoading(false);
    }
  }, []);

  const loadSyncRecordingsList = useCallback(async () => {
    setSyncRecordingsLoading(true);
    try {
      setSyncRecordings(await listSyncRecordings());
    } catch {
      setSyncRecordings([]);
    } finally {
      setSyncRecordingsLoading(false);
    }
  }, []);

  const handleDeleteSyncRecordingSession = async (sessionId: string) => {
    if (!window.confirm("确定要删除该双摄录制记录吗？")) return;
    try {
      await deleteSyncRecording(sessionId);
      await loadSyncRecordingsList();
    } catch (error) {
      alert(error instanceof Error ? error.message : "删除失败，请稍后重试");
    }
  };

  const handleMergeSyncRecording = async (sessionId: string) => {
    setMergingSyncRecordingIds((current) => new Set(current).add(sessionId));
    try {
      const updated = await mergeSyncRecording(sessionId);
      setSyncRecordings((current) => current.map((item) => item.session_id === sessionId ? updated : item));
    } catch (error) {
      alert(error instanceof Error ? error.message : "视频合并提交失败，请稍后重试");
      await loadSyncRecordingsList();
    } finally {
      setMergingSyncRecordingIds((current) => {
        const next = new Set(current);
        next.delete(sessionId);
        return next;
      });
    }
  };

  const recordingGroups = groupRecordingsByFieldSession(fieldSessions, recordings);

  useEffect(() => {
    // 预加载 sync recordings（无论当前 tab），用于 upload tab 排除双摄派生任务
    // eslint-disable-next-line react-hooks/set-state-in-effect -- starts external task-list requests.
    void loadSyncRecordingsList();
    if (sourceFilter === "recorded") {
      void loadRecordings();
      void loadFieldSessions();
    }
  }, [sourceFilter, loadRecordings, loadFieldSessions, loadSyncRecordingsList]);

  // 录制列表轮询（有活跃录制时）
  useEffect(() => {
    if (sourceFilter !== "recorded") return;
    const hasActiveRecording = recordings.some((s) => s.status === "recording");
    if (!hasActiveRecording) return;
    const interval = window.setInterval(() => {
      void loadRecordings();
    }, 3000);
    return () => window.clearInterval(interval);
  }, [sourceFilter, recordings, loadRecordings]);

  useEffect(() => {
    if (sourceFilter !== "sync_recording" || !syncRecordings.some((item) => item.merge_status === "running")) return;
    const interval = window.setInterval(() => { void loadSyncRecordingsList(); }, 2500);
    return () => window.clearInterval(interval);
  }, [sourceFilter, syncRecordings, loadSyncRecordingsList]);

  const loadJobs = useCallback(async ({ silent = false }: { silent?: boolean } = {}) => {
    if (!silent) {
      setIsRefreshing(true);
    }
    try {
      const nextJobs = await listAnalysisJobs();
      setJobs(nextJobs);
      setLoadError(null);
    } catch (error) {
      setLoadError(errorToNotice("读取分析任务失败", "无法读取任务列表，请检查后端服务或稍后重试。", error));
      setJobs([]);
    } finally {
      if (!silent) {
        setIsRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;

    const tick = async () => {
      if (!alive) {
        return;
      }
      try {
        const nextJobs = await listAnalysisJobs();
        if (!alive) {
          return;
        }
        setJobs(nextJobs);
        setLoadError(null);
        if (nextJobs.some(isActiveAnalysisJob)) {
          timer = window.setTimeout(tick, 2200);
        }
      } catch (error) {
        if (!alive) {
          return;
        }
        setLoadError(errorToNotice("读取分析任务失败", "无法读取任务列表，请检查后端服务或稍后重试。", error));
        setJobs([]);
      }
    };

    tick();

    return () => {
      alive = false;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, []);

  const visibleJobs = jobs ?? [];
  /** sync recording 的 session_id 集合（用于判断分析任务是否属于双摄录制） */
  const syncSessionIds = useMemo(
    () => new Set(syncRecordings.map(sr => sr.session_id)),
    [syncRecordings],
  );
  /** 双摄录制派生的分析任务：recordingSessionId 或 metadata.recording_session_id 必须命中 sync session */
  const recordingDerivedJobs = useMemo(
    () => visibleJobs.filter(j => {
      const sid = j.recordingSessionId ?? j.metadata.recording_session_id;
      return sid ? syncSessionIds.has(sid) : false;
    }),
    [visibleJobs, syncSessionIds],
  );
  /** 上传 tab 显示的任务列表（排除双摄录制派生） */
  const uploadJobs = useMemo(
    () => visibleJobs.filter(j => {
      const sid = j.recordingSessionId ?? j.metadata.recording_session_id;
      return !sid || !syncSessionIds.has(sid);
    }),
    [visibleJobs, syncSessionIds],
  );
  /** 按当前排序配置渲染的上传任务列表（排序不改变统计与批量删除的可见集） */
  const sortedUploadJobs = useMemo(
    () => sortAnalysisJobs(uploadJobs, sortKey, sortDir),
    [uploadJobs, sortKey, sortDir],
  );
  /** 失败/取消的终端任务：一键清除的目标 */
  const terminalJobs = useMemo(
    () => uploadJobs.filter(isTerminalAnalysisJob),
    [uploadJobs],
  );
  const terminalJobIds = terminalJobs.map((job) => job.id);
  const activeCount = visibleJobs.filter(isActiveAnalysisJob).length;
  const completedCount = visibleJobs.filter((job) => job.status === "completed").length;
  const failedCount = visibleJobs.filter((job) => job.status === "failed").length;
  const canceledCount = visibleJobs.filter((job) => job.status === "canceled").length;
  const eligibleJobs = visibleJobs.filter((job) => !isActiveAnalysisJob(job));
  const eligibleJobIds = eligibleJobs.map((job) => job.id);
  const eligibleJobKey = eligibleJobIds.join("|");
  const selectedEligibleIds = selectedJobIds.filter((jobId) => eligibleJobIds.includes(jobId));
  const isDeleting = deletingJobIds.length > 0;

  /** 上传 tab 内可删除任务：「按类型选择」只作用于这些可见任务 */
  const uploadEligibleJobs = useMemo(
    () => uploadJobs.filter((job) => !isActiveAnalysisJob(job)),
    [uploadJobs],
  );
  /** 「按类型选择」弹层的三个分析模式行：可删任务计数 + 勾选三态 */
  const modeRows = useMemo(
    () =>
      ANALYSIS_MODES.map((mode) => {
        const eligibleIds = uploadEligibleJobs.filter((job) => job.analysisMode === mode).map((job) => job.id);
        return {
          mode,
          eligibleCount: eligibleIds.length,
          state: modeSelectionState(eligibleIds, selectedJobIds),
        };
      }),
    [uploadEligibleJobs, selectedJobIds],
  );

  /** 按「类型筛选」过滤后的上传任务列表（默认全部） */
  const filteredUploadJobs = useMemo(
    () => (modeFilter === "all" ? sortedUploadJobs : sortedUploadJobs.filter((job) => job.analysisMode === modeFilter)),
    [sortedUploadJobs, modeFilter],
  );
  /** 当前筛选下可见的可删除任务：全选与已选计数按此范围计算 */
  const visibleEligibleIds = useMemo(
    () => filteredUploadJobs.filter((job) => !isActiveAnalysisJob(job)).map((job) => job.id),
    [filteredUploadJobs],
  );
  const selectedVisibleIds = selectedJobIds.filter((jobId) => visibleEligibleIds.includes(jobId));
  const allVisibleSelected = visibleEligibleIds.length > 0 && visibleEligibleIds.every((jobId) => selectedJobIds.includes(jobId));

  useEffect(() => {
    // Keep selections valid after the server-side job list changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- removes deleted/ineligible selections.
    setSelectedJobIds((current) => current.filter((jobId) => eligibleJobIds.includes(jobId)));
  }, [eligibleJobKey]);

  const buildDeleteToast = (
    deleted: number,
    blocked: number,
    failed: number,
    missing: number,
    unit: string,
  ): DeleteToastData => {
    const parts: string[] = [];
    if (blocked) parts.push(`受保护 ${blocked}`);
    if (missing) parts.push(`未找到 ${missing}`);
    if (failed) parts.push(`失败 ${failed}`);
    if (parts.length === 0) {
      return { kind: "success", message: `已删除 ${deleted} 个${unit}` };
    }
    return {
      kind: "attention",
      message: `已删除 ${deleted} 个${unit}，${parts.length} 个未删除（${parts.join(" · ")}）`,
    };
  };

  const summarizeDeleteResults = (results: Awaited<ReturnType<typeof deleteAnalysisJobs>>) => {
    const deleted = results.filter((result) => result.status === "deleted").length;
    const blocked = results.filter((result) => result.status === "blocked").length;
    const missing = results.filter((result) => result.status === "not_found").length;
    const failed = results.filter((result) => result.status === "failed").length;
    setDeleteToast(buildDeleteToast(deleted, blocked, failed, missing, "任务"));
  };

  const toggleSelection = (jobId: string) => {
    setDeleteToast(null);
    setSelectedJobIds((current) => (
      current.includes(jobId) ? current.filter((item) => item !== jobId) : [...current, jobId]
    ));
  };

  const toggleSelectAll = () => {
    setDeleteToast(null);
    setSelectedJobIds(allVisibleSelected ? [] : visibleEligibleIds);
  };

  /** 按类型筛选：选择某模式即过滤列表；点击当前激活项回到「全部」 */
  const handleSelectModeFilter = (mode: AnalysisModeFilter) => {
    updateModeFilter(modeFilter === mode ? "all" : mode);
  };

  /** 按类型选择：勾选 = 加入该类全部可删任务，取消 = 同步移除（复用同一选择集） */
  const handleToggleMode = (mode: AnalysisModeValue, check: boolean) => {
    setDeleteToast(null);
    const eligibleIds = uploadEligibleJobs.filter((job) => job.analysisMode === mode).map((job) => job.id);
    setSelectedJobIds((current) => applyModeSelection(current, eligibleIds, check));
  };

  /** 来源 tab 切换：同时收起「按类型选择」弹层 */
  const switchSourceFilter = (filter: "upload" | "recorded" | "sync_recording") => {
    setModeSelectOpen(false);
    setSourceFilter(filter);
  };

  const handleSingleDelete = async (job: AnalysisJobSummary) => {
    if (isActiveAnalysisJob(job) || isDeleting) {
      return;
    }
    const confirmed = window.confirm(`确定删除「${job.metadata.matchTitle}」吗？后端会同步删除该任务的本地产物，无法恢复。`);
    if (!confirmed) {
      return;
    }
    setDeletingJobIds([job.id]);
    setDeleteToast(null);
    try {
      const result = await deleteAnalysisJob(job.id);
      summarizeDeleteResults([result]);
      setSelectedJobIds((current) => current.filter((jobId) => jobId !== job.id));
      await loadJobs({ silent: true });
    } catch {
      setDeleteToast({ kind: "attention", message: "删除任务失败，没有删除任何任务，请检查后端服务后重试" });
    } finally {
      setDeletingJobIds([]);
    }
  };

  const handleCancelJob = async (job: AnalysisJobSummary) => {
    if (!isCancelableAnalysisJob(job) || cancelingJobIds.includes(job.id)) {
      return;
    }
    const confirmed = window.confirm(`确定取消「${job.metadata.matchTitle}」吗？运行中的任务会在安全检查点停止。`);
    if (!confirmed) {
      return;
    }
    setCancelingJobIds((current) => [...current, job.id]);
    setDeleteToast(null);
    try {
      const nextJob = await cancelAnalysisJob(job.id);
      setJobs((current) => current?.map((item) => (item.id === nextJob.id ? nextJob : item)) ?? [nextJob]);
      rememberAnalysisJob(nextJob);
      setDeleteToast({
        kind: "success",
        message:
          nextJob.status === "canceled"
            ? "任务已取消，生成的临时产物已由后端清理"
            : "已请求取消任务，运行中的分析会在安全检查点停止",
      });
      await loadJobs({ silent: true });
    } catch {
      setDeleteToast({ kind: "attention", message: "取消任务失败，无法取消该分析任务，请刷新后重试" });
    } finally {
      setCancelingJobIds((current) => current.filter((jobId) => jobId !== job.id));
    }
  };

  const handleBatchDelete = async () => {
    if (!selectedEligibleIds.length || isDeleting) {
      return;
    }
    const confirmed = window.confirm(`确定批量删除 ${selectedEligibleIds.length} 个历史分析任务吗？本地任务产物会被同步删除，无法恢复。`);
    if (!confirmed) {
      return;
    }
    setDeletingJobIds(selectedEligibleIds);
    setDeleteToast(null);
    try {
      const results = await deleteAnalysisJobs(selectedEligibleIds);
      summarizeDeleteResults(results);
      const deletedIds = results.filter((result) => result.status === "deleted" || result.status === "not_found").map((result) => result.job_id);
      setSelectedJobIds((current) => current.filter((jobId) => !deletedIds.includes(jobId)));
      await loadJobs({ silent: true });
    } catch {
      setDeleteToast({ kind: "attention", message: "批量删除失败，没有删除任何任务，请检查后端服务后重试" });
    } finally {
      setDeletingJobIds([]);
    }
  };

  const handleSortChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const [key, dir] = event.target.value.split(":") as [AnalysisSortKey, AnalysisSortDir];
    setSortKey(key);
    setSortDir(dir);
  };

  const handleClearTerminal = async () => {
    if (!terminalJobIds.length || isDeleting) {
      return;
    }
    const confirmed = window.confirm(
      `确定清除全部 ${terminalJobIds.length} 个失败/取消任务吗？本地任务产物会被同步删除，无法恢复。`,
    );
    if (!confirmed) {
      return;
    }
    setDeletingJobIds(terminalJobIds);
    setDeleteToast(null);
    try {
      const results = await deleteAnalysisJobs(terminalJobIds);
      summarizeDeleteResults(results);
      const deletedIds = results.filter((result) => result.status === "deleted" || result.status === "not_found").map((result) => result.job_id);
      setSelectedJobIds((current) => current.filter((jobId) => !deletedIds.includes(jobId)));
      await loadJobs({ silent: true });
    } catch {
      setDeleteToast({ kind: "attention", message: "清除失败/取消任务失败，没有删除任何任务，请检查后端服务后重试" });
    } finally {
      setDeletingJobIds([]);
    }
  };

  return (
    <PageFrame>
      <section className="grid gap-6 lg:grid-cols-[1fr_0.38fr] lg:items-stretch">
        <div className="sport-card p-6 sm:p-8">
          <p className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">
            <Camera size={16} aria-hidden="true" />
            视频分析
          </p>
          <h1 className="mt-3 text-4xl font-black text-[#14241B] sm:text-5xl">分析任务管理</h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600">
            这里汇总从上传到完成的所有视觉分析任务。任务由后端队列和 worker 执行，阶段耗时、错误码和结果产物会被保留，方便产品调试和科研复现。
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button className="green-button px-4 py-2.5" onClick={() => onNavigate("/analysis/new")} type="button">
              <Upload size={16} aria-hidden="true" />
              上传比赛
            </button>
            <button className="quiet-button px-4 py-2.5" onClick={() => loadJobs()} disabled={isRefreshing} type="button">
              <RefreshCw size={16} aria-hidden="true" />
              {isRefreshing ? "刷新中" : "刷新任务"}
            </button>
            <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate("/vision")} type="button">
              查看演示
            </button>
          </div>
        </div>
        <div className="grid gap-3 rounded-3xl border border-[#DDE9D6] bg-white/75 p-5 shadow-sm">
          {(sourceFilter === "upload"
            ? [
              ["全部任务", uploadJobs.length],
              ["分析中", activeCount],
              ["已完成", completedCount],
              ["失败", failedCount],
              ["已取消", canceledCount],
            ]
            : sourceFilter === "sync_recording"
              ? [
                ["全部双摄", syncRecordings.length],
                ["录制中", syncRecordings.filter((s) => s.status === "recording").length],
                ["已完成", syncRecordings.filter((s) => s.status === "completed").length],
                ["可预览", syncRecordings.filter((s) => !!s.registered_video_ids?.cam_1 || !!s.default_analysis_video_id).length],
                ["失败/取消", syncRecordings.filter((s) => s.status === "failed" || s.status === "canceled").length],
              ]
              : [
                ["全部录制", recordings.length],
                ["录制中", recordings.filter((s) => s.status === "recording").length],
                ["已完成", recordings.filter((s) => s.status === "completed").length],
                ["失败/取消", recordings.filter((s) => s.status === "failed" || s.status === "canceled").length],
              ]
          ).map(([label, value]) => (
                <div className="flex items-center justify-between rounded-2xl bg-[#F5FAF1] px-4 py-3" key={label}>
                  <span className="text-sm font-bold text-slate-500">{label}</span>
                  <strong className="text-2xl font-black text-[#14241B]">{value}</strong>
                </div>
              ))}
        </div>
      </section>

      {loadError ? (
        <div className="mt-6">
          <DiagnosticNoticeCard notice={loadError} />
        </div>
      ) : null}

      {/* 来源切换 Tab */}
      <div className="mt-6 flex gap-2">
        <button
          className={`px-5 py-2.5 rounded-full text-sm font-bold transition ${
            sourceFilter === "upload" ? "bg-[#17231D] text-white" : "bg-[#F1F7EC] text-slate-600 hover:bg-[#E8F2DC]"
          }`}
          onClick={() => switchSourceFilter("upload")}
          type="button"
        >
          <Upload size={14} className="inline mr-1.5" />
          上传视频任务
        </button>
        <button
          className={`px-5 py-2.5 rounded-full text-sm font-bold transition ${
            sourceFilter === "recorded" ? "bg-[#17231D] text-white" : "bg-[#F1F7EC] text-slate-600 hover:bg-[#E8F2DC]"
          }`}
          onClick={() => switchSourceFilter("recorded")}
          type="button"
        >
          <Camera size={14} className="inline mr-1.5" />
          录制视频任务
        </button>
        <button
          className={`px-5 py-2.5 rounded-full text-sm font-bold transition ${
            sourceFilter === "sync_recording" ? "bg-[#17231D] text-white" : "bg-[#F1F7EC] text-slate-600 hover:bg-[#E8F2DC]"
          }`}
          onClick={() => switchSourceFilter("sync_recording")}
          type="button"
        >
          <Camera size={14} className="inline mr-1.5" />
          双摄录制
        </button>
      </div>

      {/* 上传视频任务列表 */}
      {sourceFilter === "upload" && (
        <>
          {jobs === null ? (
            <section className="mt-6 sport-card p-8 text-center">
              <p className="text-sm font-bold text-[#168A34]">正在读取任务列表</p>
              <p className="mt-2 text-sm text-slate-500">正在连接后端并同步历史分析任务。</p>
            </section>
          ) : uploadJobs.length === 0 ? (
            <section className="mt-6 sport-card p-8 text-center">
              <p className="text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">暂无分析任务</p>
              <h2 className="mt-3 text-3xl font-black text-[#14241B]">先上传一场比赛</h2>
              <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-slate-600">
                上传视频并完成四角标定后，任务会出现在这里，状态会从排队、分析中更新到分析完成。
                {recordingDerivedJobs.length > 0 && (
                  <><br />通过录制创建的分析任务可在「双摄录制」tab 里查看。</>
                )}
              </p>
              <button className="green-button mx-auto mt-5" onClick={() => onNavigate("/analysis/new")} type="button">上传比赛</button>
            </section>
          ) : (
            <section className="mt-6 grid gap-4">
              <div className="flex flex-col gap-3 rounded-3xl border border-[#DDE9D6] bg-white/75 p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
                  <label className="inline-flex items-center gap-3 text-sm font-bold text-[#14241B]">
                    <input checked={allVisibleSelected} className="size-4 accent-[#22C55E]" disabled={!visibleEligibleIds.length || isDeleting} onChange={toggleSelectAll} type="checkbox" />
                    已选 {selectedVisibleIds.length} / {visibleEligibleIds.length} 个可删除历史任务
                  </label>
                  <div className="relative">
                    <button
                      aria-expanded={modeSelectOpen}
                      aria-haspopup="menu"
                      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm font-semibold outline-none transition focus:border-[#22C55E]/70 focus:ring-2 focus:ring-[#22C55E]/20 ${
                        modeFilter !== "all"
                          ? "border-[#17231D] bg-[#17231D] text-white hover:bg-[#0F1A14]"
                          : "border-[#D8E5D2] bg-white text-[#203127] hover:bg-[#F5FAF1]"
                      }`}
                      disabled={!modeRows.some((row) => row.eligibleCount > 0) || isDeleting}
                      onClick={() => setModeSelectOpen((open) => !open)}
                      type="button"
                    >
                      <ListFilter
                        aria-hidden="true"
                        className={modeFilter !== "all" ? "text-white/80" : "text-slate-500"}
                        size={15}
                      />
                      按类型选择{modeFilter !== "all" && (
                        <span className="font-bold">· {analysisModeLabel(modeFilter)}</span>
                      )}
                    </button>
                    <AnalysisModeSelectPopover
                      modeFilter={modeFilter}
                      onClose={() => setModeSelectOpen(false)}
                      onSelectModeFilter={handleSelectModeFilter}
                      onToggleMode={handleToggleMode}
                      open={modeSelectOpen}
                      rows={modeRows}
                    />
                  </div>
                  <label className="inline-flex items-center gap-2 text-sm font-semibold text-[#203127]">
                    <ArrowDownUp size={16} className="text-slate-500" aria-hidden="true" />
                    排序
                    <select
                      aria-label="任务排序"
                      className="rounded-lg border border-[#D8E5D2] bg-white px-2.5 py-1.5 text-sm font-semibold text-[#203127] outline-none transition focus:border-[#22C55E]/70 focus:ring-2 focus:ring-[#22C55E]/20"
                      onChange={handleSortChange}
                      value={`${sortKey}:${sortDir}`}
                    >
                      <option value="updatedAt:desc">更新时间 新→旧</option>
                      <option value="createdAt:desc">创建时间 新→旧</option>
                      <option value="createdAt:asc">创建时间 旧→新</option>
                      <option value="updatedAt:asc">更新时间 旧→新</option>
                    </select>
                  </label>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button className="quiet-button px-4 py-2.5" disabled={!selectedEligibleIds.length || isDeleting} onClick={() => setSelectedJobIds([])} type="button">清空选择</button>
                  <button className="green-button px-4 py-2.5" disabled={!selectedEligibleIds.length || isDeleting} onClick={handleBatchDelete} type="button">
                    <Trash2 size={16} aria-hidden="true" />{isDeleting ? "删除中" : "批量删除"}
                  </button>
                  <button className="danger-button px-4 py-2.5" disabled={!terminalJobIds.length || isDeleting} onClick={handleClearTerminal} type="button">
                    <Trash2 size={16} aria-hidden="true" />{isDeleting ? "清除中" : `清除失败/取消${terminalJobIds.length ? ` (${terminalJobIds.length})` : ""}`}
                  </button>
                </div>
              </div>
              {filteredUploadJobs.map((job) => (
                <AnalysisTaskCard
                  canceling={cancelingJobIds.includes(job.id)}
                  deleting={deletingJobIds.includes(job.id)}
                  job={job}
                  key={job.id}
                  onCancel={handleCancelJob}
                  onDelete={handleSingleDelete}
                  onNavigate={onNavigate}
                  onToggleSelected={toggleSelection}
                  recent={recentJob?.id === job.id}
                  selectable={!isActiveAnalysisJob(job)}
                  selected={selectedJobIds.includes(job.id)}
                />
              ))}
            </section>
          )}
        </>
      )}

      {/* 录制视频任务列表（按采集任务分组） */}
      {sourceFilter === "recorded" && (
        <>
          {recordingsLoading || fieldSessionsLoading ? (
            <section className="mt-6 sport-card p-8 text-center">
              <p className="text-sm font-bold text-[#168A34]">正在读取录制列表</p>
            </section>
          ) : fieldSessions.length === 0 && recordings.length === 0 ? (
            <section className="mt-6 sport-card p-8 text-center">
              <p className="text-sm font-bold uppercase tracking-[0.18em] text-[#168A34]">暂无录制视频</p>
              <h2 className="mt-3 text-3xl font-black text-[#14241B]">先去球场采集录制</h2>
              <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-slate-600">
                在球场采集页面注册摄像头并录制比赛后，所有录制记录会在这里统一管理。
              </p>
              <button className="green-button mx-auto mt-5" onClick={() => onNavigate("/camera")} type="button">前往球场采集</button>
            </section>
          ) : (
            <section className="mt-6 grid gap-4">
              {/* 批量删除工具栏 */}
              <div className="flex flex-col gap-3 rounded-3xl border border-[#DDE9D6] bg-white/75 p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
                <label className="inline-flex items-center gap-3 text-sm font-bold text-[#14241B]">
                  <input
                    checked={recordings.filter(r => r.status !== "recording").length > 0
                      && recordings.filter(r => r.status !== "recording").every(r => selectedRecordingIds.has(r.session_id))}
                    className="size-4 accent-[#22C55E]"
                    disabled={!recordings.some(r => r.status !== "recording") || isBatchDeleting}
                    onChange={handleSelectAllRecordings}
                    type="checkbox"
                  />
                  已选 {selectedRecordingIds.size} / {recordings.filter(r => r.status !== "recording").length} 个可删除录制
                </label>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="quiet-button px-4 py-2.5"
                    disabled={!selectedRecordingIds.size || isBatchDeleting}
                    onClick={() => setSelectedRecordingIds(new Set())}
                    type="button"
                  >
                    清空选择
                  </button>
                  <button
                    className="green-button px-4 py-2.5"
                    disabled={!selectedRecordingIds.size || isBatchDeleting}
                    onClick={handleBatchDeleteRecordings}
                    type="button"
                  >
                    <Trash2 size={16} aria-hidden="true" />
                    {isBatchDeleting ? "删除中" : "批量删除"}
                  </button>
                </div>
              </div>

              {/* 采集任务操作工具栏 */}
              <div className="flex flex-col gap-3 rounded-3xl border border-[#DDE9D6] bg-white/75 p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3 text-sm font-bold text-[#14241B]">
                  <input
                    checked={fieldSessions.length > 0 && fieldSessions.every(fs => selectedFieldSessionIds.has(fs.id))}
                    className="size-4 accent-[#22C55E]"
                    disabled={!fieldSessions.length || isFieldSessionBatchDeleting}
                    onChange={() => {
                      if (fieldSessions.every(fs => selectedFieldSessionIds.has(fs.id))) {
                        setSelectedFieldSessionIds(new Set());
                      } else {
                        setSelectedFieldSessionIds(new Set(fieldSessions.map(fs => fs.id)));
                      }
                    }}
                    type="checkbox"
                  />
                  已选 {selectedFieldSessionIds.size} / {fieldSessions.length} 个采集任务
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="quiet-button px-4 py-2.5"
                    disabled={!selectedFieldSessionIds.size || isFieldSessionBatchDeleting}
                    onClick={() => setSelectedFieldSessionIds(new Set())}
                    type="button"
                  >
                    清空选择
                  </button>
                  <button
                    className="green-button px-4 py-2.5"
                    disabled={!selectedFieldSessionIds.size || isFieldSessionBatchDeleting}
                    onClick={handleBatchDeleteFieldSessions}
                    type="button"
                  >
                    <Trash2 size={16} aria-hidden="true" />
                    {isFieldSessionBatchDeleting ? "删除中" : "批量删除采集任务"}
                  </button>
                  <button
                    className="quiet-button px-4 py-2.5"
                    disabled={isFieldSessionBatchDeleting}
                    onClick={handleCleanEmptyFieldSessions}
                    type="button"
                  >
                    <Trash2 size={16} aria-hidden="true" />
                    清理空采集任务
                  </button>
                </div>
              </div>

              {recordingGroups.map((group) => (
                <FieldSessionGroupCard
                  key={group.fieldSession?.id ?? "uncategorized"}
                  fieldSession={group.fieldSession}
                  recordings={group.recordings}
                  onNavigate={onNavigate}
                  onRefresh={() => { void loadRecordings(); void loadFieldSessions(); }}
                  onPlay={handlePlaySession}
                  onDeleteFieldSession={handleDeleteFieldSession}
                  selectedRecordingIds={selectedRecordingIds}
                  onToggleSelectRecording={handleToggleSelectRecording}
                  selectedFieldSession={group.fieldSession ? selectedFieldSessionIds.has(group.fieldSession.id) : false}
                  onToggleSelectFieldSession={group.fieldSession ? () => handleToggleSelectFieldSession(group.fieldSession!.id) : undefined}
                />
              ))}
            </section>
          )}
        </>
      )}

      {/* 双摄录制任务列表 */}
      {sourceFilter === "sync_recording" && (
        <>
          {syncRecordingsLoading ? (
            <section className="mt-8 text-center py-12 rounded-2xl bg-[#F1F7EC]/60">
              <RefreshCw size={20} className="mx-auto mb-3 text-slate-300 animate-spin" />
              <p className="text-sm text-slate-400">正在读取双摄录制列表</p>
            </section>
          ) : syncRecordings.length === 0 ? (
            <section className="mt-8 text-center py-12 rounded-2xl border border-dashed border-[#DDE9D6]">
              <Camera size={28} className="mx-auto mb-3 text-slate-300" />
              <p className="text-sm font-bold text-slate-500 mb-1">暂无双摄录制记录</p>
              <p className="text-xs text-slate-400 mb-4">前往采集控制台开始双摄同步录制</p>
              <button
                className="green-button inline-flex items-center gap-2 px-4 py-2 text-sm"
                onClick={() => onNavigate("/capture" as AppPath)}
                type="button"
              >
                进入采集
              </button>
            </section>
          ) : (
            <section className="mt-6 grid gap-4">
              {syncRecordings.map((sr) => (
                <SyncRecordingTaskCard
                  key={sr.session_id}
                  session={sr}
                  onDelete={handleDeleteSyncRecordingSession}
                  onNavigate={onNavigate}
                  onPlay={handlePlaySyncSession}
                  onMerge={handleMergeSyncRecording}
                  merging={mergingSyncRecordingIds.has(sr.session_id)}
                  analysisJobs={recordingDerivedJobs.filter(j =>
                    j.recordingSessionId === sr.session_id || j.metadata.recording_session_id === sr.session_id
                  )}
                />
              ))}
            </section>
          )}
        </>
      )}

      {/* 内联播放器（录制视频 Tab） */}
      {sourceFilter === "recorded" && playingSession && (
        <Modal isOpen onClose={handleClosePlayer} title={`录播回放 · ${playingSession.session_id}`} size="lg">
          <p className="mb-3 text-xs text-slate-400">{playingSession.camera_id} · {playingSession.court_name}{playingSession.duration_sec ? ` · ${playingSession.duration_sec.toFixed(0)}秒` : ""}</p>
          {playbackError ? (
            <div className="rounded-xl border border-[#FF4D4F]/25 bg-[#FF4D4F]/8 p-8 text-center">
              <p className="text-sm font-semibold text-[#C92A2A] mb-2">视频播放失败</p>
              <button className="mt-3 quiet-button px-4 py-1.5 text-xs" onClick={() => setPlaybackError(false)} type="button">重试</button>
            </div>
          ) : (
            <video key={playingSession.session_id} className="w-full rounded-xl bg-black" controls autoPlay src={getVideoStreamUrl(playingSession.video_id)} onError={() => setPlaybackError(true)} />
          )}
        </Modal>
      )}

      {sourceFilter === "sync_recording" && playingSyncSession && (
        <Modal isOpen onClose={handleCloseSyncPlayer} title={`双摄回放 · ${playingSyncSession.session_id}`} size="xl">
          <div className="mb-3 flex flex-wrap gap-3 text-xs text-slate-400">
            <span>{playingSyncSession.court_name || "未命名球场"}</span>
            {playingSyncSession.duration_sec ? <span>{playingSyncSession.duration_sec.toFixed(0)}秒</span> : null}
            <span>{playingSyncSession.segments?.length ?? 0} 个同步分段</span>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {(["cam_1", "cam_2"] as const).map((role) => {
              const slot = playingSyncSession.camera_slots?.[role];
              const videoId = playingSyncSession.registered_video_ids?.[role] ?? (role === "cam_1" ? playingSyncSession.default_analysis_video_id : undefined);
              const hasError = syncPlaybackErrors[role];
              return (
                <section className="rounded-xl border border-[#DDE9D6] bg-[#F8FBF4] p-3" key={role}>
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <h3 className="text-sm font-black text-[#14241B]">{role === "cam_1" ? "底线机位 A" : "底线机位 B"}</h3>
                    <span className="truncate text-xs font-bold text-slate-500">{slot?.camera_id ?? "未记录摄像头"}</span>
                  </div>
                  {videoId && !hasError ? (
                    <video
                      className="aspect-video w-full rounded-lg bg-black object-contain"
                      controls
                      src={getVideoStreamUrl(videoId)}
                      onError={() => setSyncPlaybackErrors((current) => ({ ...current, [role]: true }))}
                    />
                  ) : (
                    <div className="flex aspect-video items-center justify-center rounded-lg bg-[#0F172A] px-4 text-center text-sm font-semibold text-white/60">
                      {hasError ? "视频播放失败" : "该机位还没有注册成可预览视频"}
                    </div>
                  )}
                </section>
              );
            })}
          </div>
        </Modal>
      )}

      {deleteToast && (
        <DeleteToast toast={deleteToast} onClose={() => setDeleteToast(null)} />
      )}
    </PageFrame>
  );
}

function AnalysisTaskCard({
  job,
  canceling = false,
  deleting = false,
  onCancel,
  onDelete,
  onNavigate,
  onToggleSelected,
  recent,
  selectable = false,
  selected = false,
}: {
  canceling?: boolean;
  deleting?: boolean;
  job: AnalysisJobSummary;
  onCancel: (job: AnalysisJobSummary) => void;
  onDelete: (job: AnalysisJobSummary) => void;
  onNavigate: NavigateFn;
  onToggleSelected: (jobId: string) => void;
  recent?: boolean;
  selectable?: boolean;
  selected?: boolean;
}) {
  const status = analysisStatusMeta(job.status);
  const currentStage = job.stages.find((stage) => stage.id === job.stage) ?? job.stages.find((stage) => stage.status === "active");
  const updatedAt = formatDateTime(job.updatedAt || job.createdAt);
  const canCancel = isCancelableAnalysisJob(job);

  return (
    <article className={`sport-card p-5 sm:p-6 ${recent ? "border-[#22C55E]/50" : ""}`}>
      <div className="grid gap-5 lg:grid-cols-[1fr_0.38fr] lg:items-center">
        <div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-black ${status.className}`}>{status.label}</span>
              <span className="rounded-full border border-[#DDE9D6] bg-white/80 px-3 py-1 text-xs font-bold text-slate-500">
                {analysisModeLabel(job.analysisMode)}
              </span>
              {job.enableModelInference !== undefined || job.enablePoseInference !== undefined ? (
                <span className="rounded-full border border-[#DDE9D6] bg-white/80 px-3 py-1 text-xs font-bold text-slate-500">
                  检测{job.enableModelInference ? "开" : "关"} · 姿态{job.enablePoseInference ? "开" : "关"}
                </span>
              ) : null}
              {recent ? (
                <span className="rounded-full border border-[#22C55E]/30 bg-[#22C55E]/12 px-3 py-1 text-xs font-black text-[#168A34]">
                  最近任务
                </span>
              ) : null}
            </div>
            {selectable ? (
              <label className="inline-flex items-center gap-2 text-xs font-black text-slate-500">
                <input
                  checked={selected}
                  className="size-4 accent-[#22C55E]"
                  disabled={deleting}
                  onChange={() => onToggleSelected(job.id)}
                  type="checkbox"
                />
                选择
              </label>
            ) : null}
          </div>
          <h2 className="mt-4 text-2xl font-black text-[#14241B]">{job.metadata.matchTitle}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {job.metadata.fileName} · {job.metadata.venue} · {job.metadata.athleteLabel}
          </p>
          {job.recordingSessionId || job.cameraSlot || job.metadata.recording_session_id ? (
            <div className="mt-3 inline-flex flex-wrap items-center gap-2 rounded-2xl border border-[#168A34]/20 bg-[#EAF7EE] px-3 py-1.5 text-xs">
              <span className="inline-flex items-center gap-1 font-black text-[#168A34]">
                <Video size={12} aria-hidden="true" />
                来源录制
              </span>
              {(job.cameraSlot ?? job.metadata.camera_slot) ? (
                <span className="rounded-full bg-white/80 px-2 py-0.5 font-bold text-[#14241B]">
                  {(job.cameraSlot ?? job.metadata.camera_slot) === "cam_1" ? "底线 A 机位" : "底线 B 机位"}
                </span>
              ) : null}
              <button
                className="ml-1 inline-flex items-center gap-0.5 font-bold text-[#168A34] underline-offset-2 hover:underline"
                onClick={() => onNavigate(`/capture/${job.recordingSessionId ?? job.metadata.recording_session_id}/analyze?cam=${job.cameraSlot ?? job.metadata.camera_slot ?? "cam_1"}` as AppPath)}
                type="button"
              >
                <ArrowRight size={12} aria-hidden="true" />
                返回录制
              </button>
            </div>
          ) : null}
          <div className="mt-4 grid gap-2 text-sm sm:grid-cols-3">
            <TaskMeta label="更新时间" value={updatedAt} />
            <TaskMeta label="当前阶段" value={currentStage?.label ?? job.stage} />
            <TaskMeta label="任务 ID" value={job.id} />
          </div>
          {job.status === "failed" ? (
            <p className="mt-3 rounded-2xl border border-[#FF4D4F]/20 bg-[#FF4D4F]/10 p-3 text-sm font-semibold leading-6 text-[#C92A2A]">
              {job.publicErrorMessage ?? job.errorMessage ?? currentStage?.detail ?? "分析失败，请检查后端日志或重新上传。"}
              {job.errorCode ? <span className="mt-1 block text-xs font-black uppercase">错误码：{job.errorCode}</span> : null}
            </p>
          ) : null}
          {job.status === "canceled" ? (
            <p className="mt-3 rounded-2xl border border-slate-300 bg-slate-100 p-3 text-sm font-semibold leading-6 text-slate-600">
              任务已取消{job.canceledAt ? ` · ${formatDateTime(job.canceledAt)}` : ""}。
            </p>
          ) : null}
        </div>
        <div>
          <div className="rounded-3xl border border-[#DDE9D6] bg-[#F5FAF1] p-4">
            <div className="flex items-end justify-between">
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500">进度</span>
              <strong className="text-3xl font-black text-[#168A34]">{job.progress}%</strong>
            </div>
            <div className="mt-3 h-2 rounded-full bg-[#DFEADA]">
              <span className="block h-full rounded-full bg-[#22C55E]" style={{ width: `${job.progress}%` }} />
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {job.status === "completed" ? (
              <>
                <button className="green-button px-4 py-2.5" onClick={() => onNavigate(`/analysis/${job.id}/vision`)} type="button">
                  查看分析结果
                </button>
                <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate(`/analysis/${job.id}/details`)} type="button">
                  分析详情
                </button>
              </>
            ) : (
              <button className="quiet-button px-4 py-2.5" onClick={() => onNavigate(`/analysis/${job.id}`)} type="button">
                查看任务详情
              </button>
            )}
            {job.status === "failed" ? (
              <button className="green-button px-4 py-2.5" onClick={() => onNavigate("/analysis/new")} type="button">
                重新上传
              </button>
            ) : null}
            {job.status === "canceled" ? (
              <button className="green-button px-4 py-2.5" onClick={() => onNavigate("/analysis/new")} type="button">
                新建分析
              </button>
            ) : null}
            {canCancel ? (
              <button className="quiet-button px-4 py-2.5 text-[#A45A00]" disabled={canceling} onClick={() => onCancel(job)} type="button">
                {canceling ? "取消中" : "取消任务"}
              </button>
            ) : null}
            {selectable ? (
              <button className="quiet-button px-4 py-2.5 text-[#C92A2A]" disabled={deleting} onClick={() => onDelete(job)} type="button">
                <Trash2 size={15} aria-hidden="true" />
                {deleting ? "删除中" : "删除"}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  );
}

function TaskMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-[#F5FAF1] p-3">
      <span className="block text-xs font-black uppercase tracking-[0.12em] text-slate-500">{label}</span>
      <strong className="mt-1 block break-words text-[#14241B]">{value}</strong>
    </div>
  );
}


function SyncRecordingTaskCard({
  session,
  onDelete,
  onNavigate,
  onPlay,
  onMerge,
  merging = false,
  analysisJobs = [],
}: {
  session: SyncRecordingSession;
  onDelete: (sessionId: string) => void;
  onNavigate: NavigateFn;
  onPlay: (session: SyncRecordingSession) => void;
  onMerge: (sessionId: string) => void;
  merging?: boolean;
  analysisJobs?: AnalysisJobSummary[];
}) {
  const cam1Name = session.camera_slots?.cam_1?.camera_id ?? "—";
  const cam2Name = session.camera_slots?.cam_2?.camera_id ?? "—";
  const cam1VideoId = session.registered_video_ids?.cam_1 ?? session.default_analysis_video_id;
  const cam2VideoId = session.registered_video_ids?.cam_2;
  const mergeStatus = getSyncMergeStatus(session);
  const canPlay = canUseSyncVideos(session);

  // 查找每个机位的分析任务
  // 兼容策略：优先用 cameraSlot / metadata.camera_slot，回退到 videoId 匹配 registered_video_ids
  const findCamJob = (slot: "cam_1" | "cam_2") => analysisJobs.find(j => {
    if (j.cameraSlot === slot || j.metadata.camera_slot === slot) return true;
    // 旧任务兜底：用 videoId 与该机位的 registered video 匹配
    const slotVideoId = slot === "cam_1" ? cam1VideoId : cam2VideoId;
    if (j.videoId && slotVideoId && j.videoId === slotVideoId) return true;
    return false;
  });
  const cam1Job = findCamJob("cam_1");
  const cam2Job = findCamJob("cam_2");

  const statusLabel: Record<string, string> = {
    recording: "录制中", completed: "已完成", failed: "失败", canceled: "已取消",
  };
  const statusColor: Record<string, string> = {
    recording: "bg-[#FF4D4F]/12 text-[#C92A2A]",
    completed: "bg-[#22C55E]/12 text-[#168A34]",
    failed: "bg-[#FF4D4F]/12 text-[#C92A2A]",
    canceled: "bg-slate-200 text-slate-500",
  };
  const mergeStatusLabel: Record<string, string> = {
    pending: "待合并", running: "合并中", completed: "视频已就绪", failed: "合并失败",
  };

  /** 渲染单个机位的分析按钮 */
  const renderCamAnalysisButton = (
    camLabel: string, camName: string,
    videoId: string | undefined,
    job: AnalysisJobSummary | undefined,
    slot: "cam_1" | "cam_2",
  ) => {
    if (!canPlay || !videoId) return null;
    if (!job) {
      return (
        <button
          key={slot}
          className="green-button px-3 py-2 text-xs"
          onClick={() => onNavigate(`/capture/${session.session_id}/analyze?cam=${slot}` as AppPath)}
          type="button"
        >
          分析 {camLabel} 机位
        </button>
      );
    }
    // 有分析任务：按状态决定按钮
    if (job.status === "completed") {
      return (
        <button
          key={slot}
          className="green-button px-3 py-2 text-xs"
          onClick={() => onNavigate(`/analysis/${job.id}/vision`)}
          type="button"
        >
          查看 {camLabel} 分析报告
        </button>
      );
    }
    if (job.status === "failed" || job.status === "canceled") {
      return (
        <div key={slot} className="flex items-center gap-1.5">
          <span className="rounded-full bg-[#FF4D4F]/12 px-2 py-0.5 text-xs font-bold text-[#C92A2A]">
            {job.status === "failed" ? "分析失败" : "已取消"}
          </span>
          <button
            className="quiet-button px-2 py-1.5 text-xs"
            onClick={() => onNavigate(`/capture/${session.session_id}/analyze?cam=${slot}` as AppPath)}
            type="button"
          >
            重新分析
          </button>
        </div>
      );
    }
    // 进行中
    return (
      <div key={slot} className="flex items-center gap-1.5">
        <span className="rounded-full bg-[#E8A838]/15 px-2 py-0.5 text-xs font-bold text-[#9A6500]">
          分析中 {job.progress}%
        </span>
        <button
          className="quiet-button px-2 py-1.5 text-xs underline-offset-2 hover:underline"
          onClick={() => onNavigate(`/analysis/${job.id}`)}
          type="button"
        >
          查看进度
        </button>
      </div>
    );
  };

  return (
    <div className="rounded-xl border border-[#DDE9D6] bg-white p-4">
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold text-[#14241B]">
              底线机位 A: {cam1Name}
            </span>
            <span className="text-xs text-slate-400">·</span>
            <span className="text-sm font-bold text-[#14241B]">
              底线机位 B: {cam2Name}
            </span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${statusColor[session.status] ?? ""}`}>
              {statusLabel[session.status] ?? session.status}
            </span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${mergeStatus === "completed" ? "bg-[#22C55E]/12 text-[#168A34]" : mergeStatus === "failed" ? "bg-[#FF4D4F]/12 text-[#C92A2A]" : "bg-[#E8A838]/15 text-[#9A6500]"}`}>
              {mergeStatusLabel[mergeStatus] ?? mergeStatus}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
            {session.duration_sec != null && (
              <span>时长: {Math.floor(session.duration_sec / 60)}分{Math.floor(session.duration_sec % 60)}秒</span>
            )}
            <span>分段: {session.segments?.length ?? 0}</span>
            <span>可预览: {canPlay ? "A / B" : "合并完成后可用"}</span>
            {session.total_restarts > 0 && <span className="text-[#E8A838]">重启 {session.total_restarts} 次</span>}
          </div>
        </div>
      </div>
      {(session.error_message || session.merge_error) && (
        <p className="mt-2 text-xs text-[#FF4D4F] truncate">{session.merge_error || session.error_message}</p>
      )}
      {canPlay && session.default_analysis_video_id && (
        <div className="mt-3 pt-3 border-t border-[#DDE9D6]">
          <span className="text-xs text-[#168A34] font-bold">默认分析视频已就绪</span>
        </div>
      )}
      {/* 分析状态行 */}
      {(cam1Job || cam2Job) && (
        <div className="mt-2 flex flex-wrap gap-2 border-t border-[#DDE9D6] pt-3">
          {cam1Job && (
            <div className="flex items-center gap-2 rounded-full bg-[#EAF7EE] px-3 py-1 text-xs">
              <span className="font-bold text-[#168A34]">A 机位</span>
              {cam1Job.status === "completed" ? (
                <span className="text-[#168A34]">分析完成</span>
              ) : cam1Job.status === "failed" ? (
                <span className="text-[#C92A2A]">分析失败</span>
              ) : (
                <span className="text-[#9A6500]">分析中 {cam1Job.progress}%</span>
              )}
            </div>
          )}
          {cam2Job && (
            <div className="flex items-center gap-2 rounded-full bg-[#EAF7EE] px-3 py-1 text-xs">
              <span className="font-bold text-[#168A34]">B 机位</span>
              {cam2Job.status === "completed" ? (
                <span className="text-[#168A34]">分析完成</span>
              ) : cam2Job.status === "failed" ? (
                <span className="text-[#C92A2A]">分析失败</span>
              ) : (
                <span className="text-[#9A6500]">分析中 {cam2Job.progress}%</span>
              )}
            </div>
          )}
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2 border-t border-[#DDE9D6] pt-3">
        {(mergeStatus === "pending" || mergeStatus === "failed") && session.status === "completed" && (
          <button className="green-button inline-flex items-center gap-1 px-3 py-2 text-xs" onClick={() => onMerge(session.session_id)} disabled={merging} type="button">
            <RefreshCw size={12} className={merging ? "animate-spin" : ""} />
            {mergeStatus === "failed" ? "重新合并" : "合并视频"}
          </button>
        )}
        {mergeStatus === "running" && (
          <span className="self-center text-xs font-semibold text-[#9A6500]">正在后台合并两路视频...</span>
        )}
        {canPlay && (
          <button className="quiet-button px-3 py-2 text-xs" onClick={() => onPlay(session)} type="button">
            <Play size={12} className="inline mr-1" />查看双路视频
          </button>
        )}
        {canPlay && (
          <button className="quiet-button px-3 py-2 text-xs" onClick={() => onNavigate(`/recording/${session.session_id}`)} type="button">
            <LayoutDashboard size={12} className="inline mr-1" />工作台
          </button>
        )}
        {renderCamAnalysisButton("A", cam1Name, cam1VideoId, cam1Job, "cam_1")}
        {renderCamAnalysisButton("B", cam2Name, cam2VideoId, cam2Job, "cam_2")}
        {session.field_session_id && (
          <button className="quiet-button px-3 py-2 text-xs" onClick={() => onNavigate(`/capture/${session.field_session_id}` as AppPath)} type="button">
            返回采集
          </button>
        )}
        {session.status !== "recording" && (
          <button className="quiet-button px-3 py-2 text-xs text-[#C92A2A]" onClick={() => onDelete(session.session_id)} type="button">
            <Trash2 size={12} className="inline mr-1" />删除
          </button>
        )}
        {!canPlay && session.status === "completed" && mergeStatus !== "running" && (
          <span className="self-center text-xs text-slate-400">{mergeStatus === "failed" ? "视频合并失败，请重试" : "视频尚未合并"}</span>
        )}
      </div>
    </div>
  );
}
