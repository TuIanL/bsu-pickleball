import { describe, expect, it } from "vitest";
import structuredVisualizationFixture from "../test/fixtures/structured-visualization.zone-stats.v1.json";
import type { AnalysisReport } from "../types/report";
import { buildPlayerReportEvidence } from "./buildPlayerReportEvidence";
import type { PlayerReportEvidenceSources } from "./evidenceTypes";
import type { ShotRallyEventsArtifact } from "../types/shotRallyEvents";
import type { MetricSnapshotArtifact } from "../types/shotRallyEvents";
import {
  normalizeCanonicalPlayerAlias,
  resolveGlobalPlayerId,
  resolveCanonicalPlayerId,
} from "./playerIdentity";

function jobSources(overrides: Partial<PlayerReportEvidenceSources> = {}): PlayerReportEvidenceSources {
  const report = {
    source: "job",
    shotRows: [],
    metrics: {},
    performanceInsights: null,
  } as unknown as AnalysisReport;
  return { report, roster: null, serveEvents: null, trajectories: null, ...overrides };
}

describe("playerIdentity", () => {
  it("语法别名归一化：P1 / player_1 / Player_1 → Player_1", () => {
    expect(normalizeCanonicalPlayerAlias("P1")).toBe("Player_1");
    expect(normalizeCanonicalPlayerAlias("player_1")).toBe("Player_1");
    expect(normalizeCanonicalPlayerAlias("Player_1")).toBe("Player_1");
    expect(normalizeCanonicalPlayerAlias("Player_3")).toBe("Player_3");
  });

  it("global_player_N 不是语法别名，normalizeCanonicalPlayerAlias 返回 null", () => {
    expect(normalizeCanonicalPlayerAlias("global_player_1")).toBeNull();
  });

  it("全局身份只能经 roster 映射，禁止按尾号猜", () => {
    expect(
      resolveGlobalPlayerId("global_player_1", { global_player_1: "Player_3" })
    ).toBe("Player_3");
    expect(resolveGlobalPlayerId("global_player_1", null)).toBeNull();
    expect(resolveGlobalPlayerId("global_player_1", undefined)).toBeNull();
    expect(resolveGlobalPlayerId("global_player_1", {})).toBeNull();
  });

  it("resolveCanonicalPlayerId：全局走 roster，legacy 走语法", () => {
    const roster = { global_player_2: "Player_1" };
    expect(resolveCanonicalPlayerId("global_player_2", roster)).toBe("Player_1");
    expect(resolveCanonicalPlayerId("P2", roster)).toBe("Player_2");
    expect(resolveCanonicalPlayerId("global_player_4", roster)).toBeNull();
  });
});

describe("buildPlayerReportEvidence — job 源 evidence-only", () => {
  it("缺速度/进区率/距离/发球深度/轨迹时一律 unavailable，不出现近似值", () => {
    const ev = buildPlayerReportEvidence(jobSources(), "Player_1");

    expect(ev.summary.ballSpeedMph.status).toBe("unavailable");
    expect(ev.summary.paddleSpeedMph.status).toBe("unavailable");
    expect(ev.summary.inRatePct.status).toBe("unavailable");
    expect(ev.courtCoverage.distanceFt.status).toBe("unavailable");
    expect(ev.serveReturn.serveInRatePct.status).toBe("unavailable");
    expect(ev.serveReturn.serveDepth.status).toBe("unavailable");
    expect(ev.serveReturn.returnDepth.status).toBe("unavailable");
    expect(ev.trajectories.status).toBe("unavailable");
  });

  it("无真实距离时 reason 明确，绝不回退 727", () => {
    const ev = buildPlayerReportEvidence(jobSources(), "Player_1");
    if (ev.courtCoverage.distanceFt.status === "unavailable") {
      expect(ev.courtCoverage.distanceFt.reason).toContain("暂无移动距离数据");
    }
  });

  it("轨迹缺失/空 points 时 unavailable，不生成伪 points", () => {
    const traj = [
      { id: "t1", points: [], shotId: "s1", hitterPlayerId: "Player_1" },
    ] as unknown as PlayerReportEvidenceSources["trajectories"];
    const ev = buildPlayerReportEvidence(jobSources({ trajectories: traj }), "Player_1");
    expect(ev.trajectories.status).toBe("unavailable");
  });

  it("只从 structured visualization 的 canonical zone_stats 读取区域统计与 provenance", () => {
    const visualization = structuredVisualizationFixture as PlayerReportEvidenceSources["visualization"];
    const ev = buildPlayerReportEvidence(jobSources({ visualization, visualizationState: "available" }), "Player_1");
    expect(ev.courtCoverage.zoneStats.status).toBe("available");
    if (ev.courtCoverage.zoneStats.status === "available") {
      expect(ev.courtCoverage.zoneStats.value.id).toBe("Player_1");
      expect(ev.courtCoverage.zoneStats.provenance[0]?.kind).toBe("structured_visualization");
      expect(ev.courtCoverage.zoneStats.provenance[0]?.playerId).toBe("Player_1");
    }
  });

  it("structured artifact 缺失或 canonical player 不匹配时区域统计明确 unavailable", () => {
    const missing = buildPlayerReportEvidence(jobSources({ visualizationState: "unavailable", visualizationReason: "该历史任务未生成结构化区域统计" }), "Player_1");
    expect(missing.courtCoverage.zoneStats.status).toBe("unavailable");

    const visualization = {
      court: { court_width_ft: 20, court_length_ft: 44 },
      scatter_plots: { players: [], ball: [], bounces: [] },
      player_trajectories: [],
      zone_stats: { players: [{ id: "Player_2", label: "P2", color: "#000", denominator_seconds: 1, tracked_seconds: 1, data_sufficiency: "sufficient", kitchen_control_rate: 0, avg_distance_to_kitchen_line_m: 0, zones: [] }] },
    } as PlayerReportEvidenceSources["visualization"];
    const unmatched = buildPlayerReportEvidence(jobSources({ visualization, visualizationState: "available" }), "Player_1");
    expect(unmatched.courtCoverage.zoneStats.status).toBe("unavailable");
  });
});

describe("buildShotExploration — ordinal 方案 A（带 authority gate）", () => {
  it("有 rally_id 时，同一 rally 内 ordinal 确定性递增；跨 rally 重置", () => {
    const report = {
      source: "job",
      shotRows: [
        { id: "s1", player: "Player_1", type: "发球", qualityScore: 1, rally_id: "R1" },
        { id: "s2", player: "Player_2", type: "接发", qualityScore: 1, rally_id: "R1" },
        { id: "s3", player: "Player_1", type: "第三拍", qualityScore: 0.9, rally_id: "R1" },
        { id: "s4", player: "Player_2", type: "发球", qualityScore: 1, rally_id: "R2" },
        { id: "s5", player: "Player_1", type: "接发", qualityScore: 1, rally_id: "R2" },
      ],
      metrics: {},
      performanceInsights: null,
    } as unknown as AnalysisReport;

    const canonicalEvents = {
      shots: report.shotRows.map((row) => ({
        shot_id: row.id,
        rally_id: (row as { rally_id?: string }).rally_id ?? null,
        ordinal_in_rally: row.id === "s1" ? 1 : row.id === "s2" ? 2 : row.id === "s3" ? 3 : row.id === "s4" ? 1 : 2,
        start_ms: 0,
        end_ms: 100,
        hitter_player_id: row.player,
        ownership_status: "confirmed",
        stage: row.type,
        shot_type: row.type,
        quality: { score: row.qualityScore, band: "high", reasons: [] },
      })),
    } as unknown as ShotRallyEventsArtifact;

    const ev = buildPlayerReportEvidence({ report, roster: null, serveEvents: null, canonicalEvents, trajectories: null }, "Player_1");

    const ords = ev.shotExploration.map((s) => ({ rid: s.rallyId, ord: s.ordinalInRally }));
    expect(ords[0]).toEqual({ rid: "R1", ord: 1 });
    expect(ords[1]).toEqual({ rid: "R1", ord: 2 });
    expect(ords[2]).toEqual({ rid: "R1", ord: 3 });
    expect(ords[3]).toEqual({ rid: "R2", ord: 1 });
    expect(ords[4]).toEqual({ rid: "R2", ord: 2 });
  });

  it("无 rally_id 时 ordinal 一律 null（阶段筛选不可靠，绝不 i+1）", () => {
    const report = {
      source: "job",
      shotRows: [
        { id: "s1", player: "Player_1", type: "发球", qualityScore: 1 },
        { id: "s2", player: "Player_1", type: "第三拍", qualityScore: 1 },
      ],
      metrics: {},
      performanceInsights: null,
    } as unknown as AnalysisReport;

    const canonicalEvents = {
      shots: report.shotRows.map((row) => ({
        shot_id: row.id,
        rally_id: null,
        ordinal_in_rally: null,
        start_ms: 0,
        end_ms: 100,
        hitter_player_id: row.player,
        ownership_status: "confirmed",
        stage: null,
        shot_type: row.type,
        quality: { score: row.qualityScore, band: "high", reasons: [] },
      })),
    } as unknown as ShotRallyEventsArtifact;

    const ev = buildPlayerReportEvidence({ report, roster: null, serveEvents: null, canonicalEvents, trajectories: null }, "Player_1");
    expect(ev.shotExploration[0].ordinalInRally).toBeNull();
    expect(ev.shotExploration[1].ordinalInRally).toBeNull();
  });
});

describe("canonical event/metric integration", () => {
  it("真实 job 只消费 canonical event 与 metric snapshot，不回退 report rows", () => {
    const report = {
      source: "job",
      shotRows: [{ id: "legacy-row", player: "Player_1", type: "伪造字段", qualityScore: 0 }],
      metrics: {},
      performanceInsights: null,
    } as unknown as AnalysisReport;
    const canonicalEvents = {
      status: "available",
      shots: [
        {
          shot_id: "shot-canonical",
          rally_id: "rally-0001",
          ordinal_in_rally: 3,
          start_ms: 1000,
          end_ms: 1200,
          hitter_player_id: "Player_1",
          ownership_status: "confirmed",
          stage: "third",
          shot_type: "third",
          quality: { score: 0.8, band: "high", reasons: [] },
        },
        {
          shot_id: "shot-ambiguous",
          rally_id: "rally-0001",
          ordinal_in_rally: 4,
          start_ms: 1300,
          end_ms: 1500,
          hitter_player_id: null,
          ownership_status: "ambiguous",
          stage: "rally_shot",
          shot_type: "rally_shot",
          quality: { score: null, band: "none", reasons: [] },
        },
      ],
    } as unknown as ShotRallyEventsArtifact;
    const metricSnapshot = {
      status: "available",
      metrics: [
        {
          metric_id: "player:Player_1:shot_count",
          metric_key: "shot_count",
          scope: "player",
          subject_id: "Player_1",
          value: 1,
          unit: "count",
          numerator: 1,
          denominator: 1,
          sample_count: 1,
          status: "available",
          provenance: "canonical_shot_rally_events",
          evidence_ids: ["shot-canonical"],
          calculation_version: "product_reference_v1",
        },
        {
          metric_id: "player:Player_1:third_shot_count",
          metric_key: "third_shot_count",
          scope: "player",
          subject_id: "Player_1",
          value: 1,
          unit: "count",
          numerator: 1,
          denominator: 1,
          sample_count: 1,
          status: "available",
          provenance: "canonical_shot_rally_events",
          evidence_ids: ["shot-canonical"],
          calculation_version: "product_reference_v1",
        },
      ],
    } as unknown as MetricSnapshotArtifact;

    const evidence = buildPlayerReportEvidence(
      { report, canonicalEvents, metricSnapshot, roster: null, serveEvents: null, trajectories: null },
      "Player_1",
    );

    expect(evidence.shotExploration.map((shot) => shot.id)).toEqual(["shot-canonical", "shot-ambiguous"]);
    expect(evidence.summary.totalShots).toMatchObject({ status: "available", value: 1, numerator: 1, denominator: 1 });
    expect(evidence.insights.thirdShot).toMatchObject({ status: "available", value: { numerator: 1, denominator: 1 } });
  });
});

describe("architecture — pb-vizion 不得 import mock/Demo 数据", () => {
  // import.meta.glob + ?raw 拿到各组件源码文本，静态扫描禁止的 mock import（Demo 数据入口除外）。
  const modules = import.meta.glob("../components/pb-vizion/**/*.{ts,tsx}", {
    query: "?raw",
    eager: true,
    import: "default",
  }) as Record<string, string>;
  const forbidden = /(pbMockData|demoEvidence|DemoAdapter)/;

  it("报告展示组件无 mock import", () => {
    const files = Object.keys(modules);
    expect(files.length).toBeGreaterThan(0);
    for (const f of files) {
      const src = modules[f];
      for (const line of src.split("\n")) {
        if (/^\s*(import|export) /.test(line) && forbidden.test(line)) {
          throw new Error(`${f} 引入了 mock/Demo 数据: ${line.trim()}`);
        }
      }
    }
  });
});
