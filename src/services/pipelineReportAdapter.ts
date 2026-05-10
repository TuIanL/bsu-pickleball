import { demoAnalysisReport } from "../data/demoData";
import type {
  AnalysisJobSummary,
  AnalysisPipelineResult,
  AnalysisReport,
  CourtPoint,
  DashboardMetric,
  MovementPoint,
  PlayerMarker,
  ReportDefinition,
} from "../types/report";

export function isPipelineResult(value: AnalysisPipelineResult | AnalysisJobSummary | null): value is AnalysisPipelineResult {
  return Boolean(value && "job_id" in value && "metrics" in value);
}

export function adaptPipelineResultToReport(
  job: AnalysisJobSummary,
  result: AnalysisPipelineResult | null,
  fallback: AnalysisReport = demoAnalysisReport
): AnalysisReport {
  if (!result) {
    return {
      ...fallback,
      source: "job",
      jobId: job.id,
      reportId: job.reportId ?? `PV-${job.id.toUpperCase()}`,
      generatedAt: job.updatedAt,
      metadata: job.metadata,
      match: {
        ...fallback.match,
        title: job.metadata.matchTitle,
        subtitle: "真实上传视频 · pipeline 结果不可用",
        date: job.metadata.matchDate,
        venue: job.metadata.venue,
        currentRally: "结果暂不可用",
      },
      coachNotes: [
        {
          id: "result-unavailable",
          tone: "risk",
          title: "pipeline 结果暂不可用",
          body: "任务状态已完成，但前端没有读取到 raw algorithm result。请检查后端输出文件或重新运行分析。",
        },
      ],
    };
  }

  const tracks = result.tracks;
  const trackIds = new Set(tracks.map((track) => track.track_id));
  const totalDistance = sum(result.metrics.distances.map((item) => item.distance_ft));
  const averageSpeed = mean(result.metrics.speeds.map((item) => item.average_speed_ft_per_s));
  const maxSpeed = Math.max(0, ...result.metrics.speeds.map((item) => item.max_speed_ft_per_s));
  const kitchenSeconds = sum(result.metrics.kitchen_dwell.map((item) => item.kitchen_seconds));
  const limited = job.analysisMode === "limited" || !job.calibrationId;
  const noTracks = tracks.length === 0;
  const summary = noTracks
    ? limited
      ? "本次任务未提供有效场地标定，因此只保留上传与任务状态，不生成场地投影移动指标。"
      : "本次任务已处理上传视频，但当前 MVP 没有生成可用球员轨迹。请检查四角标定、拍摄角度、模型依赖和视频清晰度。"
    : `本次分析基于上传视频生成，检测到 ${trackIds.size} 条球员轨迹、${tracks.length} 个场地坐标点，累计移动距离约 ${totalDistance.toFixed(1)} 英尺。`;

  const dashboardMetrics = createDashboardMetrics(totalDistance, averageSpeed, maxSpeed, kitchenSeconds, tracks.length);
  const reportDefinitions = createReportDefinitions(dashboardMetrics, {
    averageSpeed,
    kitchenSeconds,
    limited,
    maxSpeed,
    noTracks,
    totalDistance,
  });

  return {
    ...fallback,
    source: "job",
    jobId: job.id,
    reportId: job.reportId ?? `PV-${job.id.toUpperCase()}`,
    generatedAt: result.generated_at,
    metadata: job.metadata,
    match: {
      ...fallback.match,
      title: job.metadata.matchTitle,
      subtitle: limited ? "真实上传视频 · 未标定有限分析" : "真实上传视频 · MVP 移动分析",
      date: job.metadata.matchDate,
      venue: job.metadata.venue,
      teams: job.metadata.athleteLabel,
      score: "MVP",
      currentRally: noTracks ? "未生成可用轨迹" : "移动轨迹分析",
      currentTime: "完成",
      duration: "pipeline",
    },
    session: {
      ...fallback.session,
      athlete: job.metadata.athleteLabel,
      venue: job.metadata.venue,
      date: job.metadata.matchDate,
      level: job.metadata.level,
      reportId: job.reportId ?? `PV-${job.id.toUpperCase()}`,
      summary,
      landingPoints: heatmapToCourtPoints(result),
      routes: [],
      movementPath: tracksToMovementPath(result),
      rallies: [
        {
          id: "mvp-movement",
          title: "MVP 移动分析",
          duration: "已完成",
          shots: 0,
          pattern: "当前版本暂不识别击球与回合",
          result: noTracks ? "轨迹不可用" : "移动指标可用",
          observation: "报告只展示上传视频可支持的移动、速度、站位和热力图指标，不编造球路或战术事件。",
        },
      ],
    },
    dashboardMetrics,
    reportDefinitions,
    playerMarkers: tracksToPlayerMarkers(result),
    shotTrajectories: [],
    videoOverlayLabels: [
      {
        id: "source-real",
        label: "真实上传视频",
        tone: "training",
        x: 50,
        y: 18,
      },
      {
        id: limited ? "limited" : "movement",
        label: limited ? "缺少标定" : `${tracks.length} 个轨迹点`,
        tone: limited || noTracks ? "risk" : "advantage",
        x: 53,
        y: 42,
      },
    ],
    timelineMarkers: [
      {
        id: "pipeline",
        time: "完成",
        position: 88,
        label: result.message,
        tone: limited || noTracks ? "risk" : "advantage",
      },
    ],
    highlights: [
      {
        id: "movement-summary",
        title: "移动轨迹摘要",
        time: "MVP",
        result: "算法输出",
        tone: limited || noTracks ? "risk" : "advantage",
        description: summary,
      },
    ],
    coachNotes: [
      {
        id: "real-source",
        tone: "training",
        title: "数据来源已切换为上传视频",
        body: "本页优先展示后端 pipeline 产出的移动和轨迹指标，样例击球与战术内容不再混作真实结论。",
      },
      {
        id: "movement-evidence",
        tone: noTracks ? "risk" : "advantage",
        title: noTracks ? "轨迹暂不可用" : "移动指标",
        body: noTracks
          ? "当前没有可用球员轨迹，建议重新标定四角或确认模型推理配置。"
          : `累计移动 ${totalDistance.toFixed(1)} 英尺，平均速度 ${averageSpeed.toFixed(1)} 英尺/秒，最高速度 ${maxSpeed.toFixed(1)} 英尺/秒。`,
      },
    ],
    diagnoses: [
      {
        id: "mvp-limited-diagnosis",
        issue: "动作诊断暂不可用",
        severity: "低",
        evidence: "当前 MVP 未接入姿态动作诊断模型。",
        suggestion: "先使用移动距离、速度和热力图作为训练反馈依据。",
        expectedOutcome: "避免把样例动作诊断误认为上传视频结论。",
        priority: "说明",
      },
    ],
    trainingRecommendations: [],
    drillRecommendations: [
      {
        id: "drill-court-coverage",
        title: "场地覆盖与回位节奏",
        goal: "围绕热区和移动路径做 5 组回位练习。",
        duration: "18 分钟",
        evidence: summary,
        difficulty: "进阶",
        linkedReport: "movement",
      },
    ],
    shotRows: [],
    skillRatings: [
      {
        id: "movement-coverage",
        label: "移动数据完整度",
        score: clamp(tracks.length * 8),
        note: "分数来自可用轨迹点数量，不代表技术评分。",
      },
    ],
    progressPoints: [
      {
        match: "本次上传",
        performance: clamp(Math.round(totalDistance)),
        errors: 0,
        thirdShot: 0,
        kitchen: clamp(Math.round(kitchenSeconds * 10)),
      },
    ],
  };
}

function createDashboardMetrics(
  totalDistance: number,
  averageSpeed: number,
  maxSpeed: number,
  kitchenSeconds: number,
  pointCount: number
): DashboardMetric[] {
  return [
    metric("distance", "activity", "累计移动距离", `${totalDistance.toFixed(1)} ft`, "来自场地投影轨迹的累计距离", "真实视频", clamp(totalDistance)),
    metric("avg-speed", "timer", "平均移动速度", `${averageSpeed.toFixed(1)} ft/s`, `最高速度 ${maxSpeed.toFixed(1)} ft/s`, "pipeline", clamp(averageSpeed * 12)),
    metric("kitchen", "waves", "厨房区停留", `${kitchenSeconds.toFixed(1)}s`, "按投影点统计的非截击区停留时间", "真实视频", clamp(kitchenSeconds * 10)),
    metric("tracks", "radar", "可用轨迹点", String(pointCount), "用于生成可视化和热力图的点数量", "算法输出", clamp(pointCount * 8)),
  ];
}

function createReportDefinitions(
  movementMetrics: DashboardMetric[],
  context: {
    averageSpeed: number;
    kitchenSeconds: number;
    limited: boolean;
    maxSpeed: number;
    noTracks: boolean;
    totalDistance: number;
  }
): ReportDefinition[] {
  const unavailable = "当前 MVP 未生成该类战术/击球/动作数据。";
  const sourceNote = context.limited
    ? "未提供有效标定，移动报告处于有限模式。"
    : context.noTracks
      ? "pipeline 已完成，但没有检测到可用球员轨迹。"
      : "来自上传视频的 pipeline 结果。";

  return [
    {
      type: "landing",
      title: "落点分析暂不可用",
      eyebrow: "落点分析报告",
      summary: unavailable,
      heroMetric: "N/A",
      heroMetricLabel: "球/落点检测",
      visualization: "heat",
      metrics: [metric("landing-na", "alert", "落点检测", "未接入", unavailable, "MVP 限制", 0)],
      insights: [note("landing-note", "risk", "不编造落点", "当前只展示移动与站位指标，落点需要后续球检测能力。")],
      trainingLink: "先查看移动覆盖报告",
    },
    {
      type: "movement",
      title: "移动与场地覆盖报告",
      eyebrow: "移动分析报告",
      summary: sourceNote,
      heroMetric: `${context.totalDistance.toFixed(1)} ft`,
      heroMetricLabel: "累计移动距离",
      visualization: "movement",
      metrics: movementMetrics,
      insights: [
        note("movement-source", "training", "真实 pipeline 输出", sourceNote),
        note("movement-speed", context.noTracks ? "risk" : "advantage", "速度与覆盖", `平均速度 ${context.averageSpeed.toFixed(1)} ft/s，最高速度 ${context.maxSpeed.toFixed(1)} ft/s。`),
      ],
      trainingLink: "基于移动路径安排回位训练",
    },
    {
      type: "rally",
      title: "回合战术暂不可用",
      eyebrow: "回合战术报告",
      summary: unavailable,
      heroMetric: "N/A",
      heroMetricLabel: "回合切分",
      visualization: "rally",
      metrics: [metric("rally-na", "alert", "回合识别", "未接入", unavailable, "MVP 限制", 0)],
      insights: [note("rally-note", "risk", "不编造战术", "回合、击球类型和战术模式需要球轨迹与击球事件识别。")],
      trainingLink: "先完成移动覆盖训练",
    },
    {
      type: "diagnosis",
      title: "动作诊断暂不可用",
      eyebrow: "动作诊断报告",
      summary: unavailable,
      heroMetric: "N/A",
      heroMetricLabel: "姿态诊断",
      visualization: "diagnosis",
      metrics: [metric("diagnosis-na", "alert", "动作诊断", "未接入", unavailable, "MVP 限制", 0)],
      insights: [note("diagnosis-note", "training", "需要姿态模型", "RTMPose 或同等姿态模型接入后才能输出动作证据。")],
      trainingLink: "先依据移动指标训练",
    },
  ];
}

function heatmapToCourtPoints(result: AnalysisPipelineResult): CourtPoint[] {
  const cells = result.metrics.heatmap.cells;
  const maxCount = Math.max(1, ...cells.map((cell) => cell.count));
  return cells.map((cell, index) => ({
    id: `heat-${index}`,
    x: ((cell.col + 0.5) / result.metrics.heatmap.cols) * 100,
    y: ((cell.row + 0.5) / result.metrics.heatmap.rows) * 100,
    intensity: Math.min(1, cell.count / maxCount),
    label: `热区 ${cell.row + 1}-${cell.col + 1}`,
  }));
}

function tracksToMovementPath(result: AnalysisPipelineResult): MovementPoint[] {
  const firstTrackId = result.tracks[0]?.track_id;
  return result.tracks
    .filter((track) => track.track_id === firstTrackId)
    .slice(0, 24)
    .map((track) => ({
      x: 12 + (track.court_point.x / 20) * 76,
      y: (track.court_point.y / 44) * 100,
    }));
}

function tracksToPlayerMarkers(result: AnalysisPipelineResult): PlayerMarker[] {
  const latest = new Map<string, AnalysisPipelineResult["tracks"][number]>();
  result.tracks.forEach((track) => latest.set(track.track_id, track));
  const colors = ["#22C55E", "#D9FF3F", "#2F80ED", "#FF9500"];
  return Array.from(latest.entries()).slice(0, 4).map(([trackId, track], index) => ({
    id: trackId,
    label: String.fromCharCode("A".charCodeAt(0) + index),
    team: index < 2 ? "near" : "far",
    x: 12 + (track.court_point.x / 20) * 76,
    y: 7 + (track.court_point.y / 44) * 42,
    color: colors[index % colors.length],
  }));
}

function metric(
  id: string,
  icon: string,
  label: string,
  value: string,
  detail: string,
  trend: string,
  progress: number
): DashboardMetric {
  const normalizedProgress = clamp(progress);
  return {
    id,
    icon,
    label,
    value,
    detail,
    trend,
    direction: "steady",
    progress: normalizedProgress,
    sparkline: [Math.max(0, normalizedProgress - 18), Math.max(0, normalizedProgress - 10), normalizedProgress, normalizedProgress],
  };
}

function note(id: string, tone: "advantage" | "risk" | "error" | "training", title: string, body: string) {
  return { id, tone, title, body };
}

function clamp(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function sum(values: number[]) {
  return values.reduce((total, value) => total + value, 0);
}

function mean(values: number[]) {
  return values.length ? sum(values) / values.length : 0;
}
