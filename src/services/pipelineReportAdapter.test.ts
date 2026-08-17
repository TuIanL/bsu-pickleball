import { describe, expect, it } from "vitest";
import {
  playerSideFromId,
  tracksToPlayerMarkers,
} from "./pipelineReportAdapter";
import type { AnalysisPipelineResult } from "../types/report";

function makeResult(trackIds: string[]): AnalysisPipelineResult {
  return {
    job_id: "job-test",
    status: "completed",
    generated_at: "2026-08-15T00:00:00Z",
    message: "ok",
    stages: [],
    artifacts: {} as AnalysisPipelineResult["artifacts"],
    tracks: trackIds.map((track_id, index) => ({
      track_id,
      frame_index: index,
      timestamp_seconds: index,
      court_point: { x: 5 + index, y: 10 + index, valid: true },
      image_point: { x: 0, y: 0 },
      confidence: 0.9,
      side: "unknown",
    })) as AnalysisPipelineResult["tracks"],
    metrics: {
      distances: [],
      speeds: [],
      kitchen_dwell: [],
      doubles_spacing: [],
      heatmap: { rows: 0, cols: 0, cells: [] },
    },
  };
}

describe("tracksToPlayerMarkers (fix-multiview-player-identity D2)", () => {
  it("乱序输入按 Player_N 数字升序排序，team 按槽位语义分侧", () => {
    const result = makeResult(["Player_2", "Player_4", "Player_1", "Player_3"]);
    const markers = tracksToPlayerMarkers(result, true);
    expect(markers.map((m) => m.id)).toEqual([
      "Player_1",
      "Player_2",
      "Player_3",
      "Player_4",
    ]);
    expect(markers.map((m) => m.team)).toEqual(["near", "near", "far", "far"]);
    expect(markers.map((m) => m.label)).toEqual(["A", "B", "C", "D"]);
  });

  it("单打模式：Player_1=near、Player_2=far", () => {
    const result = makeResult(["Player_2", "Player_1"]);
    const markers = tracksToPlayerMarkers(result, false);
    expect(markers.map((m) => m.id)).toEqual(["Player_1", "Player_2"]);
    expect(markers.map((m) => m.team)).toEqual(["near", "far"]);
  });

  it("非 canonical track_id 回退按 court y 推断且不崩溃", () => {
    const result = makeResult(["global_player_1", "global_player_2"]);
    const markers = tracksToPlayerMarkers(result, true);
    // court_point.y 依次为 10, 11 → 均 < 22 → near
    expect(markers.every((m) => m.team === "near")).toBe(true);
    expect(markers).toHaveLength(2);
  });
});

describe("playerSideFromId", () => {
  it("双打 1/2=near、3/4=far", () => {
    expect(playerSideFromId("Player_1", true)).toBe("near");
    expect(playerSideFromId("Player_2", true)).toBe("near");
    expect(playerSideFromId("Player_3", true)).toBe("far");
    expect(playerSideFromId("Player_4", true)).toBe("far");
  });

  it("单打 1=near、2=far", () => {
    expect(playerSideFromId("Player_1", false)).toBe("near");
    expect(playerSideFromId("Player_2", false)).toBe("far");
  });

  it("非 canonical 返回 null", () => {
    expect(playerSideFromId("candidate_3", true)).toBeNull();
    expect(playerSideFromId("track_7", false)).toBeNull();
  });
});
