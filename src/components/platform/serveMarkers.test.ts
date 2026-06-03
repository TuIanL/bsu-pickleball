import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { ServeEventsArtifact } from "../../types/report";
import { ServeRallyStrip, resolveServeMarkers } from "./VideoAnalysisCard";

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

  it("renders a horizontal serve rally strip with candidate cards", () => {
    const markers = resolveServeMarkers(
      {
        ...artifact,
        status: "partial",
        coverage: {
          source_duration_seconds: 60,
          score_series_last_timestamp_seconds: 20,
          warnings: ["score_series_ends_before_source_video"],
        },
        events: [
          artifact.events[0],
          { ...artifact.events[0], id: "serve-002", timestamp_seconds: 8, seek_time_seconds: 6.5, confidence: 0.7 },
        ],
      },
      10
    );

    const html = renderToStaticMarkup(
      createElement(ServeRallyStrip, {
        currentTime: 5,
        loadState: "available",
        markers,
        onSeek: () => undefined,
        status: "partial",
        statusDetail: "partial",
      })
    );

    expect(html).toContain("发球候选导航");
    expect(html).toContain("#01");
    expect(html).toContain("#02");
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain("降级信号");
  });

  it("renders unavailable state without candidate cards", () => {
    const html = renderToStaticMarkup(
      createElement(ServeRallyStrip, {
        currentTime: 0,
        loadState: "available",
        markers: [],
        onSeek: () => undefined,
        status: "no_candidates",
        statusDetail: "没有候选",
      })
    );

    expect(html).toContain("没有候选");
    expect(html).not.toContain("#01");
  });
});
