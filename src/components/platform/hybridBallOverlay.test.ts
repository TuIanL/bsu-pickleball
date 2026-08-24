import { describe, expect, it } from "vitest";
import type { ReconstructedBallTrajectoryArtifact } from "../../types/report";
import { hasUsableHybridBallSamples, resolveHybridBallPathSegments } from "./VideoAnalysisCard";

function artifact(): ReconstructedBallTrajectoryArtifact {
  return {
    schema_version: "reconstructed_ball_trajectory.v4",
    job_id: "job-hybrid",
    status: "partial",
    detail: "estimated",
    reconstruction_mode: "hybrid_segmented",
    overall_status: "UNAVAILABLE",
    display_trajectory_status: "degraded",
    events: [],
    segments: [{
      segment_id: "flight-1",
      reconstruction_mode: "single_view_event_anchored_2_5d",
      status: "available",
      anchors: [],
      samples: [],
      primary_view_id: "cam_a",
      image_paths_by_view: {
        cam_a: [
          { frame_index: 30, timestamp_sec: 1, image_xy: [100, 100], source: "detected", provenance: "detected", confidence: 0.9 },
          { frame_index: 36, timestamp_sec: 1.2, image_xy: [140, 80], source: "interpolated", provenance: "interpolated", confidence: 0.7 },
          { frame_index: 42, timestamp_sec: 1.4, image_xy: [180, 110], source: "predicted", provenance: "predicted", confidence: 0.4 },
        ],
      },
      end_endpoint: { event_type: "bounce", timestamp_sec: 1.4, court_xy: [12, 42], outcome_classification: "in_court" },
    }],
  };
}

describe("hybrid video ball overlay", () => {
  it("uses only the requested view and clips the trail to playback time", () => {
    const value = artifact();
    expect(hasUsableHybridBallSamples(value, "cam_a")).toBe(true);
    expect(hasUsableHybridBallSamples(value, "cam_b")).toBe(false);
    expect(resolveHybridBallPathSegments(value, 1.25, "cam_a")[0].map((sample) => sample.timestamp_sec)).toEqual([1, 1.2]);
    expect(resolveHybridBallPathSegments(value, 1.25, "cam_b")).toEqual([]);
  });

  it("retains the completed segment briefly with endpoint semantics, then removes it", () => {
    const retained = resolveHybridBallPathSegments(artifact(), 2.0, "cam_a");
    expect(retained).toHaveLength(1);
    expect(retained[0].at(-1)?.endpointType).toBe("bounce");
    expect(retained[0].map((sample) => sample.provenance)).toEqual(["detected", "interpolated", "predicted"]);
    expect(resolveHybridBallPathSegments(artifact(), 2.21, "cam_a")).toEqual([]);
  });
});
