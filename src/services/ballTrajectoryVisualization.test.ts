import { describe, expect, it } from "vitest";
import type { BallTrajectoryArtifact, BallTrajectorySample, BounceEventsArtifact } from "../types/report";
import { buildBallTrajectoryVisualization } from "./ballTrajectoryVisualization";

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
    expect(trajectory.points[1].estimatedHeightFt).toBeCloseTo(trajectory.peakEstimatedHeightFt);
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
