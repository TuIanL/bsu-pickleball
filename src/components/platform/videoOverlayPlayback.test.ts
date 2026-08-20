import { describe, expect, it } from "vitest";
import { resolveDetectionFrame, resolveFusedPlayerOverlayFrame } from "./videoOverlayPlayback";
import { buildVideoOverlayHud } from "../../services/videoOverlayHud";
import type { DetectionOverlayFrame, FusedPlayerOverlayEntity, FusedPlayerOverlayFrame } from "../../types/report";

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

describe("resolveFusedPlayerOverlayFrame", () => {
  function entity(
    playerId: string,
    timestamp: number,
    evidenceType: FusedPlayerOverlayEntity["evidence_type"] = "base_observed",
    bbox: number[] | null = [0, 0, 100, 200],
  ): FusedPlayerOverlayEntity {
    return {
      player_id: playerId,
      label: playerId.replace("Player_", "P"),
      bbox,
      footpoint: bbox ? [bbox[0] + (bbox[2] - bbox[0]) / 2, bbox[3]] : null,
      evidence_type: evidenceType,
      source_confidence: 0.9,
      overlay_confidence: 0.9,
    };
  }

  function fusedFrames(
    playersByFrame: FusedPlayerOverlayFrame["players"][],
  ): FusedPlayerOverlayFrame[] {
    return playersByFrame.map((players, index) => ({
      frame_index: index,
      timestamp_seconds: index,
      players,
    }));
  }

  it("interpolates by player_id across frames", () => {
    const frames: FusedPlayerOverlayFrame[] = [
      { frame_index: 0, timestamp_seconds: 0, players: [entity("Player_3", 0, "base_observed", [0, 0, 100, 200])] },
      { frame_index: 1, timestamp_seconds: 0.4, players: [entity("Player_3", 0.4, "base_observed", [10, 0, 110, 200])] },
    ];
    const { frame } = resolveFusedPlayerOverlayFrame(frames, 0.2);
    expect(frame?.players[0].player_id).toBe("Player_3");
    expect(frame?.players[0].bbox?.[0]).toBeCloseTo(5, 1);
  });

  it("does not interpolate across a gap larger than max overlay gap", () => {
    const wideFrames = fusedFrames([
      [entity("Player_3", 0, "base_observed")],
    ]);
    wideFrames[1] = { frame_index: 1, timestamp_seconds: 2.5, players: [entity("Player_3", 2.5)] };
    const { inGap } = resolveFusedPlayerOverlayFrame(wideFrames, 1.5);
    expect(inGap).toBe(true);
  });

  it("hides predicted_only entities past their TTL", () => {
    const frames = fusedFrames([
      [entity("Player_4", 0, "predicted_only", null)],
    ]);
    frames[1] = { frame_index: 1, timestamp_seconds: 1.2, players: [entity("Player_4", 1.2, "predicted_only", null)] };
    // 中间时刻：两帧 predicted 间隔 1.2s > 0.5s TTL → 预测已中断，隐藏
    const { frame } = resolveFusedPlayerOverlayFrame(frames, 0.6);
    expect(frame?.players.length ?? 0).toBe(0);
  });

  it("keeps predicted_only entities within their TTL", () => {
    const frames = fusedFrames([
      [entity("Player_4", 0, "predicted_only", null)],
    ]);
    frames[1] = { frame_index: 1, timestamp_seconds: 0.4, players: [entity("Player_4", 0.4, "predicted_only", null)] };
    const { frame } = resolveFusedPlayerOverlayFrame(frames, 0.2);
    expect(frame?.players.some((p) => p.player_id === "Player_4")).toBe(true);
  });
});

describe("buildVideoOverlayHud bootstrap_backfill", () => {
  function overlayEntity(
    playerId: string,
    timestamp: number,
    canonical: [number, number],
    evidenceType: FusedPlayerOverlayEntity["evidence_type"] = "bootstrap_backfill",
  ): FusedPlayerOverlayEntity {
    return {
      player_id: playerId,
      label: playerId.replace("Player_", "P"),
      bbox: [0, 0, 100, 200],
      footpoint: [50, 200],
      evidence_type: evidenceType,
      source_confidence: 0.85,
      overlay_confidence: 0.85,
      canonical_court_position_ft: canonical,
    };
  }

  function overlayFrames(
    entries: Array<{ playerId: string; timestamp: number; canonical: [number, number] }>,
    evidenceType: FusedPlayerOverlayEntity["evidence_type"] = "bootstrap_backfill",
  ): FusedPlayerOverlayFrame[] {
    return entries.map((entry, index) => ({
      frame_index: index,
      timestamp_seconds: entry.timestamp,
      players: [overlayEntity(entry.playerId, entry.timestamp, entry.canonical, evidenceType)],
    }));
  }

  it("fills the bootstrap window minimap gap from overlay positions", () => {
    // 模拟：pipelineTracks 在 lock 之后才出现（t>=1.0），而 bootstrap 回填覆盖 t=0..0.3
    const bootstrapOverlay = overlayFrames([
      { playerId: "Player_1", timestamp: 0.0, canonical: [5, 10] },
      { playerId: "Player_1", timestamp: 0.1, canonical: [5.5, 12] },
      { playerId: "Player_1", timestamp: 0.2, canonical: [6, 14] },
    ]);
    const pipelineTracks: any[] = [
      { frame_index: 30, timestamp_seconds: 1.0, track_id: "Player_1", image_point: { x: 0, y: 0 }, confidence: 0.9, side: "near", court_point: { x: 7, y: 18 } },
    ];

    // 播放头在 t=0.25：pipelineTracks（t=1.0）超出 currentTime 被排除，bootstrap 回填生效
    const hud = buildVideoOverlayHud(pipelineTracks, null, null, 0.25, { overlayFrames: bootstrapOverlay });
    expect(hud.visiblePlayerCount).toBe(1);
    const player = hud.players.find((p) => p.label === "P1");
    expect(player).toBeTruthy();
    const latest = player!.latest!;
    expect(latest.x).toBeCloseTo(6, 5);
    expect(latest.y).toBeCloseTo(14, 5);
  });

  it("does not break when overlayFrames is empty", () => {
    const hud = buildVideoOverlayHud([], null, null, 0.25, { overlayFrames: [] });
    expect(hud.visiblePlayerCount).toBe(0);
    expect(() => buildVideoOverlayHud(null, null, null, 0.25, { overlayFrames: undefined })).not.toThrow();
  });

  it("merges bootstrap backfill with post-lock tracks into one continuous trajectory", () => {
    const bootstrapOverlay = overlayFrames([
      { playerId: "Player_1", timestamp: 0.0, canonical: [5, 10] },
      { playerId: "Player_1", timestamp: 0.1, canonical: [5.5, 12] },
    ]);
    const pipelineTracks: any[] = [
      { frame_index: 30, timestamp_seconds: 1.0, track_id: "Player_1", image_point: { x: 0, y: 0 }, confidence: 0.9, side: "near", court_point: { x: 7, y: 18 } },
    ];

    // 播放头在 t=1.0：bootstrap 与 pipelineTracks 都在窗口内，应合并为同一球员的多点轨迹
    const hud = buildVideoOverlayHud(pipelineTracks, null, null, 1.0, { overlayFrames: bootstrapOverlay });
    expect(hud.visiblePlayerCount).toBe(1);
    const player = hud.players.find((p) => p.label === "P1");
    expect(player).toBeTruthy();
    const totalPoints = player!.segments.reduce((sum, segment) => sum + segment.length, 0);
    expect(totalPoints).toBeGreaterThanOrEqual(3); // 2 bootstrap + 1 pipeline
  });
});
