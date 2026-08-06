import { describe, expect, it } from "vitest";
import { resolveDetectionFrame } from "./videoOverlayPlayback";
import type { DetectionOverlayFrame } from "../../types/report";

function detection(
  trackId: string,
  timestamp: number,
  playerId?: string,
  label?: string,
) {
  return {
    frame_index: timestamp * 30,
    timestamp_seconds: timestamp,
    bbox: [0, 0, 100, 200],
    confidence: 0.9,
    class_name: "person" as const,
    track_id: trackId,
    player_id: playerId,
    label,
    source_width: 1920,
    source_height: 1080,
  };
}

function frames(detectionsByFrame: DetectionOverlayFrame["detections"][]): DetectionOverlayFrame[] {
  return detectionsByFrame.map((detections, index) => ({
    frame_index: index,
    timestamp_seconds: index,
    detections,
  }));
}

describe("resolveDetectionFrame identity continuity", () => {
  it("inherits the next canonical identity for the same track", () => {
    const resolved = resolveDetectionFrame(
      frames([
        [detection("17", 0)],
        [detection("17", 1, "Player_1")],
      ]),
      0.5,
    );

    expect(resolved?.detections[0].player_id).toBe("Player_1");
    expect(resolved?.detections[0].label).toBe("P1");
  });

  it("does not infer identity across different tracks", () => {
    const resolved = resolveDetectionFrame(
      frames([
        [detection("17", 0)],
        [detection("18", 1)],
      ]),
      0.5,
    );

    expect(resolved?.detections[0].player_id).toBeUndefined();
    expect(resolved?.detections[0].label).toBeUndefined();
  });

  it("keeps canonical labels separate from raw track IDs", () => {
    const resolved = resolveDetectionFrame(
      frames([
        [detection("164", 0)],
        [detection("164", 1, "Player_2", "P2")],
      ]),
      0.5,
    );

    expect(resolved?.detections[0].label).toBe("P2");
    expect(resolved?.detections[0].label).not.toContain("164");
  });
});
