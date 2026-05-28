import { describe, expect, it } from "vitest";
import type { ServeEventsArtifact } from "../../types/report";
import { resolveServeMarkers } from "./VideoAnalysisCard";

const artifact: ServeEventsArtifact = {
  job_id: "job-1",
  status: "available",
  detail: "ok",
  detector_version: "serve-start-mvp-v1",
  fps: 30,
  frame_count: 300,
  processed_frame_count: 10,
  frame_stride: 1,
  events: [
    {
      id: "serve-001",
      timestamp_seconds: 5,
      frame_index: 150,
      confidence: 0.8,
      seek_time_seconds: 3.5,
      reason: "稳定后突增",
      source_signals: ["tracking"],
    },
  ],
};

describe("serve marker resolution", () => {
  it("maps serve events to progress positions and seek times", () => {
    const markers = resolveServeMarkers(artifact, 10);

    expect(markers).toHaveLength(1);
    expect(markers[0].position).toBe(50);
    expect(markers[0].seekTime).toBe(3.5);
  });

  it("clamps invalid seek and progress values", () => {
    const markers = resolveServeMarkers(
      {
        ...artifact,
        events: [{ ...artifact.events[0], timestamp_seconds: 12, seek_time_seconds: -1 }],
      },
      10
    );

    expect(markers[0].position).toBe(100);
    expect(markers[0].seekTime).toBe(0);
  });

  it("preserves context detector fields for marker tooltips", () => {
    const markers = resolveServeMarkers(
      {
        ...artifact,
        detector_version: "serve-moment-context-v1",
        detection_mode: "pose",
        events: [
          {
            ...artifact.events[0],
            detection_mode: "pose",
            start_time_seconds: 3,
            end_time_seconds: 9,
            signals: {
              baseline_position_score: 0.9,
              pre_stillness_score: 0.8,
              arm_motion_peak_score: 0.7,
              rally_after_score: 0.6,
            },
          },
        ],
      },
      10
    );

    expect(markers[0].detection_mode).toBe("pose");
    expect(markers[0].signals?.baseline_position_score).toBe(0.9);
    expect(markers[0].start_time_seconds).toBe(3);
  });
});
