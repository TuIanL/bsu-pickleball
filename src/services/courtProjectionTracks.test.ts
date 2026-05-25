import { describe, expect, it } from "vitest";
import { buildCourtTrackSummaries, sampleTrackPoints } from "./courtProjectionTracks";
import type { PipelineTrackPoint } from "../types/report";

describe("court projection track helpers", () => {
  it("groups projected points by track and orders summaries by persistence", () => {
    const summaries = buildCourtTrackSummaries([
      trackPoint("short", 2, 1, 3, 4, 0.7),
      trackPoint("long", 3, 0.2, 8, 10, 0.8),
      trackPoint("long", 1, 0, 7, 9, 0.9),
      trackPoint("long", 2, 0.1, 7.5, 9.5, 0.85),
    ]);

    expect(summaries).toHaveLength(2);
    expect(summaries[0]).toMatchObject({
      trackId: "long",
      label: "轨迹 1",
      pointCount: 3,
      firstFrameIndex: 1,
      latestFrameIndex: 3,
      isShortFragment: true,
    });
    expect(summaries[0].averageConfidence).toBeCloseTo(0.85);
    expect(summaries[0].bounds).toEqual({ minX: 7, maxX: 8, minY: 9, maxY: 10 });
    expect(summaries[1]).toMatchObject({
      trackId: "short",
      label: "轨迹 2",
      pointCount: 1,
      isShortFragment: true,
    });
  });

  it("marks persistent tracks and exposes stable color assignments", () => {
    const points = Array.from({ length: 14 }, (_, index) => trackPoint("primary", index, index * 0.2, index % 20, index % 44, 0.75));
    const summaries = buildCourtTrackSummaries(points);

    expect(summaries[0].isShortFragment).toBe(false);
    expect(summaries[0].color).toBe("#2F80ED");
    expect(summaries[0].durationSeconds).toBeCloseTo(2.6);
  });

  it("samples rendered points while preserving the first and latest points", () => {
    const points = Array.from({ length: 20 }, (_, index) => trackPoint("sampled", index, index, index, index, 0.8));
    const sampled = sampleTrackPoints(points, 5);

    expect(sampled).toHaveLength(5);
    expect(sampled[0].frame_index).toBe(0);
    expect(sampled[sampled.length - 1].frame_index).toBe(19);
    expect(sampled.map((point) => point.frame_index)).toEqual([...new Set(sampled.map((point) => point.frame_index))]);
  });

  it("ignores points without renderable court coordinates", () => {
    const summaries = buildCourtTrackSummaries([
      trackPoint("ok", 1, 0, 4, 5, 0.8),
      trackPoint("bad", 2, 1, Number.NaN, 3, 0.8),
    ]);

    expect(summaries).toHaveLength(1);
    expect(summaries[0].trackId).toBe("ok");
  });
});

function trackPoint(trackId: string, frameIndex: number, timestampSeconds: number, x: number, y: number, confidence: number): PipelineTrackPoint {
  return {
    confidence,
    court_point: { x, y },
    frame_index: frameIndex,
    image_point: { x: x * 10, y: y * 10 },
    side: "unknown",
    timestamp_seconds: timestampSeconds,
    track_id: trackId,
  };
}
