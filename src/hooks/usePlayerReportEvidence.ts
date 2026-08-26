// =============================================================
// usePlayerReportEvidence —— IO 层（I/O 与 pure 分离，设计 D2/D7/D8）
// -------------------------------------------------------------
// 负责把 report（及可用的 job artifact）组装成 PlayerReportEvidenceSources，
// 再调用纯转换 buildPlayerReportEvidence。
// 真实 job：按 jobId 抓取 reconstructed trajectory + serve events（权威数据），
// 失败/不可用 → 该 source 保持缺省，纯转换输出 unavailable（绝不伪造）。
// =============================================================
import { useEffect, useMemo, useState } from "react";
import type { AnalysisReport } from "../types/report";
import { buildPlayerReportEvidence } from "../evidence/buildPlayerReportEvidence";
import type { PlayerReportEvidence, PlayerReportEvidenceSources } from "../evidence/evidenceTypes";
import { resolveCanonicalPlayerId } from "../evidence/playerIdentity";
import { isPipelineResult } from "../services/pipelineReportAdapter";
import {
  getAnalysisResult,
  getStructuredVizData,
  getMetricSnapshot,
  getReconstructedBallTrajectory,
  getShotRallyEvents,
  getServeEvents,
  isAnalysisApiError,
} from "../services/analysisClient";
import { buildReconstructedBallTrajectoryVisualization } from "../services/ballTrajectoryVisualization";

/** 仅基于 report 的基线 sources（无后端抓取）。 */
function baselineSources(report: AnalysisReport): PlayerReportEvidenceSources {
  return {
    report,
    roster: null,
    serveEvents: null,
    canonicalEvents: null,
    metricSnapshot: null,
    trajectories: null,
    visualization: null,
    visualizationState: report.source === "job" ? "loading" : "unavailable",
    visualizationReason: report.source === "job" ? "正在读取结构化区域统计" : null,
  };
}

/** 真实 job：按 jobId 抓取权威 artifacts，组装 richer sources。 */
async function loadJobSources(report: AnalysisReport): Promise<PlayerReportEvidenceSources> {
  const sources = baselineSources(report);
  const jobId = report.jobId;
  if (!jobId) return sources;

  const structuredVisualization = getStructuredVizData(jobId)
    .then((data) => ({ data, state: data ? "available" as const : "unavailable" as const, reason: data ? null : "本次任务未生成结构化区域统计" }))
    .catch((error: unknown) => ({
      data: null,
      state: isAnalysisApiError(error) && error.status === 404 ? "unavailable" as const : "failed" as const,
      reason: isAnalysisApiError(error) && error.status === 404
        ? "该历史任务未生成结构化区域统计"
        : "结构化区域统计读取失败",
    }));
  try {
    const raw = await getAnalysisResult(jobId);
    if (isPipelineResult(raw)) {
      const [rec, serve, canonicalEvents, metricSnapshot] = await Promise.all([
        getReconstructedBallTrajectory(raw),
        getServeEvents(raw),
        getShotRallyEvents(raw),
        getMetricSnapshot(raw),
      ]);
      sources.canonicalEvents = canonicalEvents;
      sources.metricSnapshot = metricSnapshot;
      if (rec && !["unavailable", "failed", "skipped", "no_candidates"].includes(rec.status)) {
        const viz = buildReconstructedBallTrajectoryVisualization(rec);
        if (viz.trajectories.length > 0) {
          sources.trajectories = viz.trajectories;
        }
        if (viz.playerRoster.length) {
          sources.roster = Object.fromEntries(viz.playerRoster.map((r) => [r.player_id, r.player_id]));
        }
      }
      if (serve && serve.status === "available" && Array.isArray(serve.events)) {
        sources.serveEvents = {
          events: serve.events.map((e) => ({
            eventId: e.id,
            playerId: e.player_id ?? null,
            timestampSec: e.timestamp_seconds ?? null,
            courtXFt: Array.isArray(e.court_position) ? e.court_position[0] ?? null : null,
            courtYFt: Array.isArray(e.court_position) ? e.court_position[1] ?? null : null,
          })),
        };
      }
    }
  } catch {
    // 抓取失败 → 保持缺省，纯转换输出 unavailable（不伪造）
  }
  const visualization = await structuredVisualization;
  sources.visualization = visualization.data;
  sources.visualizationState = visualization.state;
  sources.visualizationReason = visualization.reason;
  return sources;
}

/**
 * IO hook：加载 artifact / 组装 sources → 纯转换。
 * 渲染用 `loaded ?? baseline`：无后端数据（demo / 缺 job）或加载未完成时显示同步 baseline；
 * 异步 .then 里才 setLoaded（不在 effect 同步 setState）。
 */
export function usePlayerReportEvidence(
  jobId: string | null | undefined,
  report: AnalysisReport,
  playerId: string
): PlayerReportEvidence {
  const canonicalId = useMemo(
    () => resolveCanonicalPlayerId(playerId, null) ?? playerId,
    [playerId]
  );

  const baseline = useMemo(
    () => buildPlayerReportEvidence(baselineSources(report), canonicalId),
    [report, canonicalId]
  );

  const [loaded, setLoaded] = useState<PlayerReportEvidence | null>(null);

  useEffect(() => {
    if (!report.jobId || report.source !== "job") return; // 保持 baseline
    let cancelled = false;
    loadJobSources(report)
      .then((sources) => {
        if (!cancelled) setLoaded(buildPlayerReportEvidence(sources, canonicalId));
      })
      .catch(() => {
        // 失败 → 保持 baseline（unavailable），不伪造
      });
    return () => {
      cancelled = true;
    };
  }, [report, canonicalId]);

  void jobId; // jobId 与 report.jobId 一致；签名保留为显式契约

  // 仅当异步加载结果与当前球员一致时才用它，避免跨球员渲染陈旧数据
  const display = loaded && loaded.playerId === canonicalId ? loaded : baseline;
  return display;
}
