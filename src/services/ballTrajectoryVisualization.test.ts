import { describe, expect, it } from "vitest";
import type {
  BallTrajectoryArtifact,
  BallTrajectorySample,
  BounceEventsArtifact,
  ReconstructedBallTrajectoryArtifact,
  ReconstructedBallTrajectorySegment,
} from "../types/report";
import {
  buildBallTrajectoryVisualization,
  buildReconstructedBallTrajectoryVisualization,
  buildShots,
  filterTrajectories,
  type EstimatedBallTrajectory,
} from "./ballTrajectoryVisualization";

function artifact(samples: BallTrajectorySample[]): BallTrajectoryArtifact {
  return {
    schema_version: "cleaned_ball_trajectory.v1",
    job_id: "job-1",
    status: "available",
    detail: "test",
    samples,
  };
}

function point(frame: number, timestamp: number, x: number, y: number, confidence = 0.8, interpolated = false): BallTrajectorySample {
  return { frame_index: frame, timestamp_sec: timestamp, court_xy: [x, y], confidence, interpolated };
}

describe("buildBallTrajectoryVisualization", () => {
  it("sorts valid points and creates a deterministic estimated arc", () => {
    const result = buildBallTrajectoryVisualization(artifact([
      point(2, 0.2, 10, 20),
      point(0, 0, 8, 10),
      point(1, 0.1, 9, 15),
    ]));

    expect(result.trajectories).toHaveLength(1);
    const trajectory = result.trajectories[0];
    expect(trajectory.direction).toBe("near-to-far");
    expect(trajectory.points.map((item) => item.timestampSeconds)).toEqual([0, 0.1, 0.2]);
    expect(trajectory.points[0].estimatedHeightFt).toBe(0);
    expect(trajectory.peakEstimatedHeightFt).not.toBeNull();
    expect(trajectory.points[1].estimatedHeightFt).toBeCloseTo(trajectory.peakEstimatedHeightFt as number);
    expect(trajectory.points[2].estimatedHeightFt).toBe(0);
    expect(trajectory.points.every((item) => item.heightSource === "estimated")).toBe(true);
  });

  it("splits trajectories on time gaps and planar jumps", () => {
    const result = buildBallTrajectoryVisualization(artifact([
      point(0, 0, 5, 5), point(1, 0.1, 6, 6), point(2, 0.2, 7, 7),
      point(3, 1.0, 8, 8), point(4, 1.1, 9, 9), point(5, 1.2, 10, 10),
      point(6, 1.3, 22, 22), point(7, 1.4, 21, 21), point(8, 1.5, 20, 20),
    ]), null, { boundsPaddingFt: 4 });

    expect(result.trajectories).toHaveLength(3);
  });

  it("drops invalid coordinates and segments with too few points", () => {
    const result = buildBallTrajectoryVisualization(artifact([
      point(0, 0, 5, 5),
      { frame_index: 1, timestamp_sec: 0.1, court_xy: [Number.NaN, 5] },
      point(2, 0.2, 50, 50),
    ]));

    expect(result.discardedPointCount).toBe(2);
    expect(result.trajectories).toEqual([]);
  });

  it("summarizes confidence, interpolation, and valid bounce markers", () => {
    const bounces: BounceEventsArtifact = {
      schema_version: "bounce_events.v1",
      job_id: "job-1",
      status: "available",
      detail: "test",
      events: [
        { event_id: "b1", frame_index: 2, timestamp_sec: 0.2, image_xy: [1, 1], court_xy: [10, 20], confidence: 0.9, detection_method: "test" },
        { event_id: "b2", frame_index: 3, timestamp_sec: 0.3, image_xy: [1, 1], court_xy: [40, 20], confidence: 0.9, detection_method: "test" },
      ],
    };
    const result = buildBallTrajectoryVisualization(artifact([
      point(0, 0, 5, 5, 0.9),
      point(1, 0.1, 6, 6, 0.8, true),
      point(2, 0.2, 7, 7, 0.7),
    ]), bounces);

    expect(result.trajectories[0].averageConfidence).toBeCloseTo(0.8);
    expect(result.trajectories[0].interpolatedRatio).toBeCloseTo(1 / 3);
    expect(result.trajectories[0].highConfidence).toBe(true);
    expect(result.bounces.map((bounce) => bounce.id)).toEqual(["b1"]);
  });
});

function reconstructedSegment(overrides: Partial<ReconstructedBallTrajectorySegment> = {}): ReconstructedBallTrajectorySegment {
  return {
    segment_id: "flight-1",
    reconstruction_mode: "dual_anchor_warp",
    status: "reconstructed",
    start_event_id: "hit-1",
    end_event_id: "bounce-1",
    start_event_type: "hit",
    end_event_type: "bounce",
    boundary_reason: "bounce",
    fit_space: "image_px",
    model: "weighted_huber_anchor_constrained",
    anchors: [
      { anchor_id: "anchor-hit-1", anchor_type: "contact", frame_index: 0, court_xy: [5, 10], confidence: 0.5 },
      { anchor_id: "anchor-bounce-1", anchor_type: "bounce", frame_index: 4, court_xy: [10, 22], confidence: 0.9 },
    ],
    quality: {
      overall: 0.85,
      display_level: "high",
      detection_score: 0.8,
      predicted_ratio: 0.25,
      net_crossing_status: "expected",
      observation_coverage: 0.8,
    },
    samples: [
      { frame_index: 0, timestamp_sec: 0, court_xy: [5, 10], estimated_height_ft: 3.6, source: "detected", confidence: 0.9 },
      { frame_index: 1, timestamp_sec: 0.03, court_xy: [6, 12], estimated_height_ft: 4.2, source: "model_predicted", confidence: null },
      { frame_index: 2, timestamp_sec: 0.06, court_xy: [7, 15], estimated_height_ft: 4.0, source: "detected", confidence: 0.85 },
      { frame_index: 3, timestamp_sec: 0.09, court_xy: [8, 18], estimated_height_ft: 3.1, source: "interpolated", confidence: null },
      { frame_index: 4, timestamp_sec: 0.12, court_xy: [10, 22], estimated_height_ft: 0, source: "anchor", confidence: 0.9 },
    ],
    ...overrides,
  };
}

function reconstructedArtifact(segments: ReconstructedBallTrajectorySegment[]): ReconstructedBallTrajectoryArtifact {
  return {
    schema_version: "reconstructed_ball_trajectory.v1",
    job_id: "job-1",
    status: "available",
    detail: "test",
    reconstruction_mode: "event_anchored_2_5d",
    coordinate_semantics: { xy: "court_ft_visual_estimate", z: "estimated_height_ft", metric_validity: "visualization_only" },
    events: [],
    segments,
  };
}

describe("buildReconstructedBallTrajectoryVisualization", () => {
  it("maps reconstructed segments to trajectories using artifact heights (no frontend generation)", () => {
    const result = buildReconstructedBallTrajectoryVisualization(reconstructedArtifact([reconstructedSegment()]));

    expect(result.trajectories).toHaveLength(1);
    const trajectory = result.trajectories[0];
    expect(trajectory.points.map((point) => point.estimatedHeightFt)).toEqual([3.6, 4.2, 4.0, 3.1, 0]);
    expect(trajectory.points.map((point) => point.source)).toEqual([
      "detected",
      "model_predicted",
      "detected",
      "interpolated",
      "anchor",
    ]);
    expect(trajectory.points[1].interpolated).toBe(true);
    expect(trajectory.points[0].interpolated).toBe(false);
    // 高度来自后端，不再以统一 4*peak*p*(1-p) 强制两端为零
    expect(trajectory.points[0].estimatedHeightFt).not.toBe(0);
    expect(trajectory.points[0].heightSource).toBeNull();
    expect(trajectory.peakEstimatedHeightFt).toBe(4.2);
    expect(trajectory.highConfidence).toBe(true);
    expect(trajectory.quality?.netCrossingStatus).toBe("expected");
  });

  it("exposes bounce and contact anchors as event markers", () => {
    const result = buildReconstructedBallTrajectoryVisualization(reconstructedArtifact([reconstructedSegment()]));
    const anchors = result.trajectories[0].anchors ?? [];

    expect(anchors.map((anchor) => anchor.anchorType)).toEqual(["contact", "bounce"]);
    expect(result.bounces.map((bounce) => bounce.id)).toEqual(["anchor-bounce-1"]);
  });

  it("filters out image_only / insufficient-anchor / low-quality segments", () => {
    const result = buildReconstructedBallTrajectoryVisualization(reconstructedArtifact([
      reconstructedSegment(),
      reconstructedSegment({ segment_id: "flight-2", reconstruction_mode: "image_only", status: "insufficient_spatial_anchors", quality: { overall: 0.36, display_level: "none" } }),
      reconstructedSegment({ segment_id: "flight-3", quality: { overall: 0.5, display_level: "low" } }),
    ]));

    // 轨迹 ID 使用后端稳定 segment_id（不变量：不使用前端自生成序号）
    expect(result.trajectories.map((trajectory) => trajectory.id)).toEqual(["flight-1"]);
  });

  it("returns empty data when reconstruction is unavailable", () => {
    const result = buildReconstructedBallTrajectoryVisualization(null);
    expect(result.trajectories).toEqual([]);
    expect(result.bounces).toEqual([]);
    expect(result.shots).toEqual([]);
    expect(result.playerRoster).toEqual([]);
  });
});

function trajectoryWithOwnership(
  id: string,
  shotId: string | null,
  hitter: string | null,
  ownership: "confirmed" | "ambiguous" | "unassigned" | "not_applicable",
  start: number,
  highConfidence = true,
): EstimatedBallTrajectory {
  return {
    id,
    sequence: 1,
    direction: "near-to-far",
    startTimeSeconds: start,
    endTimeSeconds: start + 0.5,
    durationSeconds: 0.5,
    pointCount: 5,
    averageConfidence: 0.8,
    interpolatedRatio: 0.1,
    highConfidence,
    peakEstimatedHeightFt: 4,
    points: [],
    shotId,
    hitterPlayerId: hitter,
    hitterRenderSlot: hitter ? hitter.replace("Player_", "slot_") : null,
    ownershipStatus: ownership,
    ownershipConfidence: ownership === "confirmed" ? 0.9 : null,
  };
}

describe("Shot 级聚合与筛选（I5）", () => {
  it("聚合同一 shot_id 的多段为一个 Shot，且统计按 shot 去重", () => {
    const trajectories = [
      trajectoryWithOwnership("flight-3", "shot-7", "Player_1", "confirmed", 1.0),
      trajectoryWithOwnership("flight-4", "shot-7", "Player_1", "confirmed", 1.6),
      trajectoryWithOwnership("flight-5", "shot-8", "Player_3", "confirmed", 2.5),
    ];
    const shots = buildShots(trajectories);
    expect(shots.map((shot) => shot.shotId)).toEqual(["shot-7", "shot-8"]);
    expect(shots[0].segments.map((segment) => segment.id)).toEqual(["flight-3", "flight-4"]);
    expect(shots[0].hitterPlayerId).toBe("Player_1");
    expect(shots[0].sequence).toBe(1);
  });

  it("P3 筛选：可见球路的 hitter_player_id 均为 Player_3", () => {
    const trajectories = [
      trajectoryWithOwnership("flight-1", "shot-1", "Player_1", "confirmed", 0.0),
      trajectoryWithOwnership("flight-2", "shot-2", "Player_3", "confirmed", 1.0),
      trajectoryWithOwnership("flight-3", "shot-2", "Player_3", "confirmed", 1.5),
    ];
    const shots = buildShots(trajectories);
    const { trajectories: filtered, shots: filteredShots } = filterTrajectories(trajectories, shots, {
      playerFilter: "Player_3",
      confidence: "all",
      displayLimit: "all",
    });
    expect(filtered.every((trajectory) => trajectory.hitterPlayerId === "Player_3")).toBe(true);
    expect(filteredShots.map((shot) => shot.shotId)).toEqual(["shot-2"]);
  });

  it("未归属筛选包含击球者不明与无 Shot 上下文两类", () => {
    const trajectories = [
      trajectoryWithOwnership("flight-1", "shot-1", "Player_1", "confirmed", 0.0),
      trajectoryWithOwnership("flight-2", "shot-2", null, "unassigned", 1.0),
      trajectoryWithOwnership("flight-3", null, null, "not_applicable", 2.0),
    ];
    const shots = buildShots(trajectories);
    const { trajectories: filtered } = filterTrajectories(trajectories, shots, {
      playerFilter: "unassigned",
      confidence: "all",
      displayLimit: "all",
    });
    expect(filtered.map((trajectory) => trajectory.id)).toEqual(["flight-2", "flight-3"]);
  });

  it("筛选顺序：球员 → 可信度 → 最近 N 条", () => {
    const trajectories = [
      trajectoryWithOwnership("flight-1", "shot-1", "Player_3", "confirmed", 0.0, false),
      trajectoryWithOwnership("flight-2", "shot-2", "Player_3", "confirmed", 1.0),
      trajectoryWithOwnership("flight-3", "shot-3", "Player_3", "confirmed", 2.0),
    ];
    const shots = buildShots(trajectories);
    const { trajectories: filtered } = filterTrajectories(trajectories, shots, {
      playerFilter: "Player_3",
      confidence: "high",
      displayLimit: 1,
    });
    expect(filtered.map((trajectory) => trajectory.id)).toEqual(["flight-3"]);
  });
});

describe("v1 产物兼容", () => {
  it("v1 产物无归属字段：球路正常展示且不伪造归属", () => {
    const result = buildReconstructedBallTrajectoryVisualization(reconstructedArtifact([reconstructedSegment()]));
    const trajectory = result.trajectories[0];
    expect(trajectory.hitterPlayerId).toBeNull();
    expect(trajectory.shotId).toBeNull();
    expect(trajectory.ownershipStatus).toBe("not_applicable");
    expect(result.playerRoster).toEqual([]);
    expect(result.shots).toEqual([]);
  });
});
