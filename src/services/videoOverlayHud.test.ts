import { describe, expect, it } from "vitest";
import type { BallTrajectoryArtifact, BounceEventsArtifact, PipelineTrackPoint } from "../types/report";
import { buildVideoOverlayHud } from "./videoOverlayHud";

function track(overrides: Partial<PipelineTrackPoint> = {}): PipelineTrackPoint {
  return {
    frame_index: 0,
    timestamp_seconds: 0,
    track_id: "Player_1",
    image_point: { x: 0, y: 0 },
    confidence: 0.9,
    side: "near",
    court_point: { x: 4, y: 5 },
    ...overrides,
  };
}

function trajectory(samples: BallTrajectoryArtifact["samples"]): BallTrajectoryArtifact {
  return {
    schema_version: "cleaned_ball_trajectory.v1",
    job_id: "job",
    status: "available",
    detail: "",
    coordinate_system: { court: "feet", court_width: 20, court_length: 44 },
    samples,
  };
}

describe("buildVideoOverlayHud", () => {
  it("uses a time window and breaks player trails at data gaps", () => {
    const result = buildVideoOverlayHud([
      track({ timestamp_seconds: 1, court_point: { x: 2, y: 2 } }),
      track({ timestamp_seconds: 1.2, court_point: { x: 3, y: 2 } }),
      track({ timestamp_seconds: 2.4, court_point: { x: 4, y: 2 } }),
      track({ timestamp_seconds: 2.6, court_point: { x: 5, y: 2 } }),
      track({ timestamp_seconds: 7, court_point: { x: 10, y: 10 } }),
    ], null, null, 3, { playerTrailSeconds: 3, maxGapSeconds: 0.7 });

    expect(result.players).toHaveLength(1);
    expect(result.players[0].segments).toHaveLength(2);
    expect(result.players[0].latest?.x).toBe(5);
    expect(result.players[0].speedMetersPerSecond).toBeCloseTo(0.3048 / 0.2, 5);
  });

  it("keeps interpolated ball points distinct and does not bridge long gaps", () => {
    const result = buildVideoOverlayHud([], trajectory([
      { frame_index: 1, timestamp_sec: 4, image_xy: [10, 10], court_xy: [3, 8], confidence: 0.9 },
      { frame_index: 2, timestamp_sec: 4.2, image_xy: [12, 12], court_xy: [4, 9], confidence: 0.7, interpolated: true },
      { frame_index: 3, timestamp_sec: 5.4, image_xy: [20, 20], court_xy: [8, 14], confidence: 0.8 },
    ]), null, 5.5, { ballTrailSeconds: 2, maxGapSeconds: 0.7 });

    expect(result.ballSegments).toHaveLength(2);
    expect(result.ballSegments[0][1].interpolated).toBe(true);
    expect(result.ballLatest?.x).toBe(8);
  });

  it("ignores invalid coordinates and marks only current bounce candidates active", () => {
    const bounces: BounceEventsArtifact = {
      schema_version: "bounce_events.v1",
      job_id: "job",
      status: "available",
      detail: "",
      events: [
        { event_id: "near", frame_index: 1, timestamp_sec: 3, image_xy: [1, 1], court_xy: [4, 8], confidence: 0.8, detection_method: "test" },
        { event_id: "bad", frame_index: 2, timestamp_sec: 3.1, image_xy: [1, 1], court_xy: [Infinity, 8], confidence: 0.9, detection_method: "test" },
      ],
    };
    const result = buildVideoOverlayHud([track({ court_point: { x: Number.NaN, y: 3 } })], null, bounces, 3.2);

    expect(result.players).toHaveLength(0);
    expect(result.bounces).toEqual([expect.objectContaining({ id: "near", active: true })]);
  });

  it("does not present a numeric speed when the coordinate unit is unknown", () => {
    const result = buildVideoOverlayHud([
      track({ timestamp_seconds: 1, court_point: { x: 2, y: 2 } }),
      track({ timestamp_seconds: 1.2, court_point: { x: 3, y: 2 } }),
    ], null, null, 1.2, { courtUnit: "unknown" });

    expect(result.players[0].speedMetersPerSecond).toBeNull();
  });

  it("marks a player as stale when its latest point lags current time beyond the threshold", () => {
    const staleResult = buildVideoOverlayHud([
      track({ timestamp_seconds: 1, court_point: { x: 2, y: 2 } }),
      track({ timestamp_seconds: 1.2, court_point: { x: 3, y: 2 } }),
    ], null, null, 2);
    // latest=1.2 < currentTime=2 - 0.5 → 停滞
    expect(staleResult.players[0].stale).toBe(true);

    const freshResult = buildVideoOverlayHud([
      track({ timestamp_seconds: 1, court_point: { x: 2, y: 2 } }),
      track({ timestamp_seconds: 1.8, court_point: { x: 3, y: 2 } }),
    ], null, null, 2);
    // latest=1.8 >= currentTime=2 - 0.5 → 非停滞
    expect(freshResult.players[0].stale).toBe(false);
  });

  it("breaks a player trail when consecutive points jump beyond the displacement threshold", () => {
    const result = buildVideoOverlayHud([
      track({ timestamp_seconds: 1, court_point: { x: 2, y: 2 } }),
      track({ timestamp_seconds: 1.03, court_point: { x: 2.1, y: 2 } }),
      // 从 (2,2) 跳到 (16,10)：位移 ~14.6ft，超过默认 6ft 阈值，且时间差小于 maxGapSeconds
      track({ timestamp_seconds: 1.06, court_point: { x: 16, y: 10 } }),
      track({ timestamp_seconds: 1.09, court_point: { x: 16.1, y: 10 } }),
    ], null, null, 1.2, { maxGapSeconds: 0.7 });

    expect(result.players).toHaveLength(1);
    // 应拆成两个 segment，不把跨越跳变的直线画进同一段
    expect(result.players[0].segments).toHaveLength(2);
    expect(result.players[0].segments[0]).toHaveLength(2);
    expect(result.players[0].segments[1]).toHaveLength(2);
  });

  it("does not break the ball trail on large displacement (time continuity wins)", () => {
    const result = buildVideoOverlayHud([], trajectory([
      { frame_index: 1, timestamp_sec: 4, image_xy: [10, 10], court_xy: [3, 8], confidence: 0.9 },
      { frame_index: 2, timestamp_sec: 4.03, image_xy: [50, 50], court_xy: [18, 30], confidence: 0.8 },
    ]), null, 4.2, { ballTrailSeconds: 2, maxGapSeconds: 0.7 });

    // 球可合法高速移动，不应按位移断线
    expect(result.ballSegments).toHaveLength(1);
    expect(result.ballSegments[0]).toHaveLength(2);
  });
});
