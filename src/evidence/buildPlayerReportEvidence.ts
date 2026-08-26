// =============================================================
// buildPlayerReportEvidence —— 纯转换（IO 与 pure 分离，设计 D2/D4）
// -------------------------------------------------------------
// sources → PlayerReportEvidence。本函数不做任何网络/加载，可单测。
// fail-closed：仅 report.source === "demo" 允许 mock；其余一律 evidence-only。
// =============================================================
import type {
  DepthDistribution,
  EvidenceRef,
  EvidenceValue,
  PlayerReportEvidence,
  PlayerReportEvidenceSources,
  ShotEvidence,
  ThirdShotStats,
} from "./evidenceTypes";
import type { TrainingRecommendation } from "../types/report";
import type { MetricSnapshotEntry } from "../types/shotRallyEvents";
import {
  sameCanonicalPlayer,
  resolveCanonicalPlayerId,
} from "./playerIdentity";
import {
  demoBallSpeedMph,
  demoInRatePct,
  demoPaddleSpeedMph,
} from "./demoEvidence";

function unavailable<T>(reason: string, provenance?: EvidenceRef[]): EvidenceValue<T> {
  return { status: "unavailable", value: null, reason, provenance };
}

function available<T>(value: T, provenance: EvidenceRef[], confidence?: number): EvidenceValue<T> {
  return { status: "available", value, provenance, confidence };
}

function metricEvidence<T extends number | ThirdShotStats>(
  metric: MetricSnapshotEntry | undefined,
  fallbackReason: string,
  transform: (metric: MetricSnapshotEntry) => T,
): EvidenceValue<T> {
  if (!metric) return unavailable(fallbackReason, [{ kind: "metric_snapshot" }]);
  const provenance: EvidenceRef[] = [
    { kind: "metric_snapshot", artifactId: "metric-snapshot.v1", field: metric.metric_key },
    ...metric.evidence_ids.map((eventId) => ({ kind: "canonical_events" as const, eventId })),
  ];
  if (metric.status === "available" && metric.value !== null) {
    return {
      status: "available",
      value: transform(metric),
      provenance,
      confidence: metric.confidence ?? undefined,
      numerator: typeof metric.numerator === "number" ? metric.numerator : undefined,
      denominator: typeof metric.denominator === "number" ? metric.denominator : undefined,
      sampleCount: metric.sample_count,
    };
  }
  const status = metric.status === "insufficient_evidence" || metric.status === "not_applicable" || metric.status === "failed"
    ? metric.status
    : "unavailable";
  return { status, value: null, reason: metric.reason ?? fallbackReason, provenance };
}

function findMetric(
  sources: PlayerReportEvidenceSources,
  metricKey: string,
  scope: "match" | "team" | "player",
  subjectId: string,
): MetricSnapshotEntry | undefined {
  return sources.metricSnapshot?.metrics.find(
    (metric) => metric.metric_key === metricKey && metric.scope === scope && metric.subject_id === subjectId,
  );
}

const NOT_GENERATED = "本次分析暂未生成";
const NO_PLAYER = "未识别到该球员数据";

/** 从 report 提取可能的 heatmap 源（metrics.heatmap / visualizations.heatmaps） */
function extractHeatmap(
  sources: PlayerReportEvidenceSources,
  playerId: string,
  roster: Record<string, string> | null | undefined
): EvidenceValue<import("../types/report").HeatmapPlayerGrid> {
  if (sources.report.source !== "demo") {
    return unavailable("真实报告不使用位置网格代替区域统计", [{ kind: "heatmap" }]);
  }
  const reportAny = sources.report as unknown as {
    metrics?: { heatmap?: { players?: import("../types/report").HeatmapPlayerGrid[] } };
    visualizations?: {
      heatmaps?: { players?: import("../types/report").HeatmapPlayerGrid[] };
    };
  };
  const pools: (import("../types/report").HeatmapPlayerGrid[] | undefined)[] = [];
  if (reportAny.metrics?.heatmap?.players) pools.push(reportAny.metrics.heatmap.players);
  if (reportAny.visualizations?.heatmaps?.players) pools.push(reportAny.visualizations.heatmaps.players);
  for (const pool of pools) {
    if (!pool) continue;
    const match = pool.find((p) => sameCanonicalPlayer(p.id, playerId, roster));
    if (match) return available(match, [{ kind: "heatmap", field: "players" }]);
  }
  return unavailable(NO_PLAYER, [{ kind: "heatmap" }]);
}

/**
 * 区域空间热力图只能消费 structured visualization 的 zone_stats。
 * 这里按 canonical identity 严格匹配，禁止根据展示名、数组位置或 heatmap 网格猜测。
 */
function extractZoneStats(
  sources: PlayerReportEvidenceSources,
  playerId: string,
  roster: Record<string, string> | null | undefined,
): EvidenceValue<import("../types/report").PlayerZoneStats> {
  const canonicalId = resolveCanonicalPlayerId(playerId, roster);
  const provenance: EvidenceRef[] = [{
    kind: "structured_visualization",
    artifactId: "structured-visualization-data",
    field: "zone_stats.players",
    playerId: canonicalId ?? undefined,
  }];
  const visualization = sources.visualization;

  if (!visualization) {
    const reason = sources.visualizationReason
      ?? (sources.visualizationState === "loading"
        ? "正在读取结构化区域统计"
        : "本次任务未生成结构化区域统计");
    return unavailable(reason, provenance);
  }

  const players = visualization.zone_stats?.players;
  if (!Array.isArray(players) || players.length === 0) {
    return unavailable("暂无区域统计", provenance);
  }
  if (!canonicalId) {
    return unavailable("当前球员未映射为 canonical player，无法关联区域统计", provenance);
  }
  const matched = players.find((player) => sameCanonicalPlayer(player.id, canonicalId, roster));
  if (!matched) {
    return unavailable("结构化区域统计中没有当前球员", provenance);
  }
  if (!Array.isArray(matched.zones) || matched.zones.length === 0) {
    return unavailable("当前球员暂无区域统计", provenance);
  }
  return available(matched, provenance);
}

/** 从 report.metrics.distances 提取跑动距离（仅真实值），否则 unavailable（绝不回退 727）。 */
function extractDistanceFt(
  sources: PlayerReportEvidenceSources,
  playerId: string,
  roster: Record<string, string> | null | undefined
): EvidenceValue<number> {
  const m = (sources.report as unknown as {
    metrics?: { distances?: Array<{ track_id?: string; player_id?: string; distance_ft?: number }> };
  }).metrics;
  const distances = m?.distances;
  if (Array.isArray(distances)) {
    for (const d of distances) {
      const id = d.track_id || d.player_id;
      if (id && sameCanonicalPlayer(id, playerId, roster) && typeof d.distance_ft === "number") {
        return available(Math.round(d.distance_ft), [
          { kind: "report", field: "metrics.distances" },
        ]);
      }
    }
  }
  // 无真实距离 → 明确 unavailable，不造 727
  return unavailable("暂无移动距离数据", [{ kind: "report", field: "metrics.distances" }]);
}

function buildSummary(
  sources: PlayerReportEvidenceSources,
  playerId: string,
  roster: Record<string, string> | null | undefined,
  isDemo: boolean
): PlayerReportEvidence["summary"] {
  const canonicalId = resolveCanonicalPlayerId(playerId, roster);
  if (!isDemo) {
    return {
      totalShots: metricEvidence(
        canonicalId ? findMetric(sources, "shot_count", "player", canonicalId) : undefined,
        "canonical Metric Snapshot 尚未生成该球员的击球统计",
        (metric) => Number(metric.value),
      ),
      inRatePct: unavailable(NOT_GENERATED, [{ kind: "metric_snapshot", field: "serve_in_rate" }]),
      ballSpeedMph: unavailable(NOT_GENERATED, [{ kind: "metric_snapshot", field: "ball_speed_mph" }]),
      paddleSpeedMph: unavailable(NOT_GENERATED, [{ kind: "metric_snapshot", field: "paddle_speed_mph" }]),
    };
  }
  const rows = Array.isArray(sources.report.shotRows) ? sources.report.shotRows : [];

  let matched = 0;
  let matchedAny = false;
  for (const row of rows) {
    if (canonicalId && sameCanonicalPlayer(row.player, playerId, roster)) {
      matched++;
      matchedAny = true;
    }
  }

  const totalShots: EvidenceValue<number> =
    matchedAny
      ? available(matched, [{ kind: "report", field: "shotRows" }])
      : available(0, [{ kind: "report", field: "shotRows" }]);

  // 进区率 / 球速 / 拍速：job 一律不造（设计 D5/清理清单）
  if (isDemo) {
    return {
      totalShots,
      inRatePct: available(demoInRatePct(playerId), [{ kind: "report", field: "demo" }]),
      ballSpeedMph: available(demoBallSpeedMph(playerId), [{ kind: "report", field: "demo" }]),
      paddleSpeedMph: available(demoPaddleSpeedMph(playerId), [{ kind: "report", field: "demo" }]),
    };
  }
  return {
    totalShots,
    inRatePct: unavailable(NOT_GENERATED),
    ballSpeedMph: unavailable(NOT_GENERATED),
    paddleSpeedMph: unavailable(NOT_GENERATED),
  };
}

function buildServeReturn(
  sources: PlayerReportEvidenceSources,
  playerId: string,
  roster: Record<string, string> | null | undefined,
  isDemo: boolean
): PlayerReportEvidence["serveReturn"] {
  const canonicalId = resolveCanonicalPlayerId(playerId, roster) ?? playerId;
  if (!isDemo) {
    return {
      serveCount: metricEvidence(
        findMetric(sources, "serve_count", "player", canonicalId),
        "canonical Metric Snapshot 尚未生成发球统计",
        (metric) => Number(metric.value),
      ),
      serveInRatePct: unavailable("发球进区率：当前事件层尚未证明合法/出界结果", [{ kind: "metric_snapshot", field: "serve_in_rate" }]),
      serveDepth: unavailable("发球深度：当前事件层尚未生成", [{ kind: "metric_snapshot", field: "serve_depth" }]),
      returnCount: metricEvidence(
        findMetric(sources, "return_count", "player", canonicalId),
        "canonical Metric Snapshot 尚未生成接发统计",
        (metric) => Number(metric.value),
      ),
      returnDepth: unavailable("接发深度：当前事件层尚未生成", [{ kind: "metric_snapshot", field: "return_depth" }]),
    };
  }
  // Serve/Return authority（设计 D7）：ServeEvents 只证明发球次数/发球者；In/Out、深度不可证明。
  let serveCount = 0;
  let serveCountAny = false;
  const events = sources.serveEvents?.events;
  if (Array.isArray(events)) {
    for (const ev of events) {
      if (sameCanonicalPlayer(ev.playerId, playerId, roster)) {
        serveCount++;
        serveCountAny = true;
      }
    }
  }

  const unavailableAll = {
    serveCount: unavailable<number>(NO_PLAYER),
    serveInRatePct: unavailable<number>("发球进区率：暂未生成"),
    serveDepth: unavailable<DepthDistribution>("发球深度：暂未生成"),
    returnCount: unavailable<number>("接发统计：暂未生成"),
    returnDepth: unavailable<DepthDistribution>("接发深度：暂未生成"),
  };

  if (isDemo) {
    return {
      serveCount: available<number>(9, [{ kind: "serve_events" }]),
      serveInRatePct: available<number>(100, [{ kind: "serve_events" }]),
      serveDepth: unavailable<DepthDistribution>("发球深度：暂未生成"),
      returnCount: available<number>(9, [{ kind: "serve_events" }]),
      returnDepth: unavailable<DepthDistribution>("接发深度：暂未生成"),
    };
  }

  return {
    ...unavailableAll,
    serveCount: serveCountAny
      ? available<number>(serveCount, [{ kind: "serve_events", field: "events" }])
      : unavailable<number>(NO_PLAYER),
  };
}

function buildTrajectories(
  sources: PlayerReportEvidenceSources
): EvidenceValue<import("../services/ballTrajectoryVisualization").EstimatedBallTrajectory[]> {
  const trajs = sources.trajectories;
  if (Array.isArray(trajs) && trajs.some((t) => t.points && t.points.length > 0)) {
    const withPoints = trajs.filter((t) => t.points && t.points.length > 0);
    if (withPoints.length > 0) {
      return available(withPoints, [{ kind: "reconstructed_trajectory" }]);
    }
  }
  return unavailable("暂无可视化球路数据", [{ kind: "reconstructed_trajectory" }]);
}

function buildInsights(
  sources: PlayerReportEvidenceSources,
  playerId: string,
): PlayerReportEvidence["insights"] {
  const pi = sources.report.performanceInsights;
  const findings = pi?.findings?.length ? pi.findings : [];
  const recommendations = pi?.recommendations?.length ? pi.recommendations : [];
  const coachNotes = (sources.report.coachNotes ?? []) as unknown as TrainingRecommendation[];

  const thirdShotMetric = findMetric(sources, "third_shot_count", "player", playerId);
  const thirdShot = thirdShotMetric
    ? metricEvidence(
      thirdShotMetric,
      "当前没有可靠的第三拍样本",
      (metric) => ({
        numerator: Number(metric.numerator ?? metric.value ?? 0),
        denominator: Number(metric.denominator ?? 0),
      }),
    )
    : unavailable<ThirdShotStats>("当前没有可靠的第三拍样本", [{ kind: "metric_snapshot", field: "third_shot_count" }]);

  return {
    findings: findings.length
      ? available(findings, [{ kind: "performance_insight", field: "findings" }])
      : unavailable("当前数据不足以生成可靠训练建议"),
    recommendations: recommendations.length
      ? available(recommendations, [{ kind: "performance_insight", field: "recommendations" }])
      : unavailable("当前数据不足以生成可靠训练建议"),
    coachNotes: coachNotes.length
      ? available(coachNotes as typeof coachNotes, [{ kind: "performance_insight", field: "coachNotes" }])
      : unavailable("当前数据不足以生成可靠训练建议"),
    thirdShot,
  };
}

/**
 * 方案 A（adapter-derived ordinal，带 authority gate）：按 rally_id 聚合、以行序（=时间序）
 * 赋 ordinalInRally。源里无 rally_id（无法判 rally 边界）→ ordinal 为 null（阶段筛选不可靠，
 * 绝不 i+1 伪造）。ordinal 只由本层产出，PB 组件不得自行推断。
 */
function buildShotExploration(sources: PlayerReportEvidenceSources): ShotEvidence[] {
  const canonical = sources.canonicalEvents;
  if (canonical) {
    return canonical.shots.map((shot) => ({
      id: shot.shot_id,
      rallyId: shot.rally_id ?? null,
      ordinalInRally: shot.ordinal_in_rally ?? null,
      playerId: shot.hitter_player_id ?? null,
      type: shot.shot_type ?? shot.stage ?? "",
      stage: shot.stage ?? null,
      startMs: shot.start_ms,
      endMs: shot.end_ms,
      ownershipStatus: shot.ownership_status,
      qualityScore: shot.quality.score ?? null,
      result: shot.result ?? null,
      errorType: shot.error_type ?? null,
      provenance: [
        { kind: "canonical_events", artifactId: "shot-rally-events.v1", eventId: shot.shot_id },
      ],
    }));
  }
  if (sources.report.source !== "demo") return [];
  const rows = Array.isArray(sources.report.shotRows) ? sources.report.shotRows : [];

  const ordinalByIndex = new Map<number, { rallyId: string | null; ordinal: number | null }>();
  {
    // 按 rally_id 分组赋序号（行序视为时间序）；无 rally_id → 一律不可靠
    const counters = new Map<string, number>();
    let hasRally = false;
    rows.forEach((row, idx) => {
      const rallyId = (row as { rally_id?: string | null }).rally_id ?? null;
      if (rallyId) {
        hasRally = true;
        const n = (counters.get(rallyId) ?? 0) + 1;
        counters.set(rallyId, n);
        ordinalByIndex.set(idx, { rallyId, ordinal: n });
      } else {
        ordinalByIndex.set(idx, { rallyId: null, ordinal: null });
      }
    });
    if (!hasRally) ordinalByIndex.clear(); // 无任何 rally 边界 → 全部 null
  }

  return rows.map((row, idx) => {
    const o = ordinalByIndex.get(idx);
    return {
      id: typeof row.id === "string" ? row.id : String(idx),
      rallyId: o?.rallyId ?? null,
      ordinalInRally: o?.ordinal ?? null,
      playerId: row.player ?? null,
      type: row.type ?? "",
      qualityScore: row.qualityScore ?? null,
      provenance: [{ kind: "report", field: "shotRows" }],
    };
  });
}

export function buildPlayerReportEvidence(
  sources: PlayerReportEvidenceSources,
  playerId: string
): PlayerReportEvidence {
  // 设计 D4：只有显式 === "demo" 才允许演示数据（fail-closed）
  const isDemo = sources.report?.source === "demo";
  const roster = sources.roster ?? null;

  const canonicalId = resolveCanonicalPlayerId(playerId, roster) ?? playerId;

  return {
    playerId: canonicalId,
    isDemo,
    summary: buildSummary(sources, playerId, roster, isDemo),
    courtCoverage: {
      distanceFt: extractDistanceFt(sources, playerId, roster),
      heatmap: extractHeatmap(sources, playerId, roster),
      zoneStats: extractZoneStats(sources, playerId, roster),
    },
    serveReturn: buildServeReturn(sources, playerId, roster, isDemo),
    shotExploration: buildShotExploration(sources),
    trajectories: buildTrajectories(sources),
    insights: buildInsights(sources, canonicalId),
  };
}
