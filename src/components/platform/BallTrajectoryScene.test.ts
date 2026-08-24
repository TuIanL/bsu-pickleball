import { describe, expect, it } from "vitest";
import type { EstimatedBallTrajectory } from "../../services/ballTrajectoryVisualization";
import { getLastRenderablePoint, splitContinuousTrajectoryPaths, splitTrajectoryRuns, VIEW_CONFIG } from "./BallTrajectoryScene";

describe("BallTrajectoryScene hybrid line encoding", () => {
  it("keeps detected, interpolated, and predicted samples in separately styled WebGL runs", () => {
    const trajectory = {
      id: "flight-webgl",
      sequence: 1,
      direction: "near-to-far",
      startTimeSeconds: 0,
      endTimeSeconds: 0.5,
      durationSeconds: 0.5,
      pointCount: 6,
      averageConfidence: 0.7,
      interpolatedRatio: 0.5,
      highConfidence: false,
      peakEstimatedHeightFt: 4,
      shotId: null,
      hitterPlayerId: null,
      hitterRenderSlot: null,
      ownershipStatus: "not_applicable",
      ownershipConfidence: null,
      points: [
        ["detected", 0], ["detected", 1],
        ["interpolated", 2], ["interpolated", 3],
        ["model_predicted", 4], ["model_predicted", 5],
      ].map(([source, index]) => ({
        frameIndex: Number(index), timestampSeconds: Number(index) / 10,
        courtXFt: 8 + Number(index), courtYFt: 10 + Number(index), estimatedHeightFt: 3,
        confidence: 0.7, interpolated: source !== "detected", heightSource: "estimated",
        source,
      })),
    } as EstimatedBallTrajectory;

    expect(splitTrajectoryRuns(trajectory).map((run) => run.style)).toEqual(["detected", "interpolated", "predicted"]);
  });

  it("provides the five PB Vision camera presets", () => {
    expect(Object.keys(VIEW_CONFIG)).toEqual(["oblique", "top", "sideline", "baseline", "obliqueBaseline"]);
    expect(Object.values(VIEW_CONFIG).map((view) => view.label)).toEqual(["45°", "俯视", "边线", "底线", "45°底线"]);
  });

  it("keeps source changes continuous but breaks long missing intervals", () => {
    const trajectory = {
      points: [
        [0, "detected"], [0.1, "interpolated"], [0.2, "predicted"], [1.1, "detected"], [1.2, "detected"],
      ].map(([time, source], index) => ({
        frameIndex: index,
        timestampSeconds: Number(time),
        courtXFt: 8 + index,
        courtYFt: 10 + index,
        estimatedHeightFt: 3,
        confidence: 0.7,
        interpolated: source !== "detected",
        heightSource: "estimated",
        source,
      })),
    } as unknown as EstimatedBallTrajectory;

    expect(splitContinuousTrajectoryPaths(trajectory)).toHaveLength(2);
    expect(splitTrajectoryRuns(trajectory).every((run) => run.points.length >= 2)).toBe(true);
  });

  it("exposes one final renderable sample as the only terminal candidate", () => {
    const trajectory = {
      points: [
        { courtXFt: 1, courtYFt: 2, estimatedHeightFt: 1 },
        { courtXFt: 2, courtYFt: 3, estimatedHeightFt: null },
        { courtXFt: 4, courtYFt: 5, estimatedHeightFt: 2 },
      ],
    } as unknown as EstimatedBallTrajectory;

    expect(getLastRenderablePoint(trajectory)?.courtXFt).toBe(4);
  });
});
