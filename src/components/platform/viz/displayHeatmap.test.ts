import { describe, expect, it } from "vitest";
import type { PlayerDisplayDiagnosticsRow } from "../../../types/report";
import { buildHeatmapMatrix } from "./displayHeatmap";

function row(overrides: Partial<PlayerDisplayDiagnosticsRow>): PlayerDisplayDiagnosticsRow {
  return {
    canonical_tick: 1,
    timestamp_ms: 1000,
    player_id: "Player_1",
    view_id: "cam_1",
    frame_status: "available",
    expected_region_status: "available",
    eligible_detections_in_expected_gate: 1,
    eligible_detection_present: true,
    position_present: true,
    court_position_present: true,
    formal_observation_emitted: true,
    formal_local_observation: true,
    local_player_id: "Player_1",
    global_associated: true,
    binding_visibility: "observed",
    available_miss_streak: 0,
    ...overrides,
  } as PlayerDisplayDiagnosticsRow;
}

describe("buildHeatmapMatrix", () => {
  it("sorts ticks ascending and fills every stage", () => {
    const { ticks, matrix, rowsByTick } = buildHeatmapMatrix([row({ canonical_tick: 3, timestamp_ms: 3000 }), row({ canonical_tick: 1, timestamp_ms: 1000 })]);
    expect(ticks).toEqual([1, 3]);
    expect(matrix).toHaveLength(2);
    expect(matrix[0]).toHaveLength(9);
    expect(matrix[0].every((value) => value === 1)).toBe(true);
    expect(rowsByTick.get(3)).toHaveLength(1);
  });

  it("marks broken stages as 2 (failed) and null fields as 0 (not triggered)", () => {
    const { matrix } = buildHeatmapMatrix([
      row({ position_present: false, court_position_present: false, formal_observation_emitted: false, global_associated: false, available_miss_streak: 3, projection_status: null }),
    ]);
    // 索引：0 期望区域 1 门内候选 2 有检测框 3 有位置 4 球场投影 5 正式观测 6 全局关联 7 绑定可见性 8 连续漏检
    expect(matrix[0][3]).toBe(2); // 有位置 失败
    expect(matrix[0][4]).toBe(2); // 球场投影 失败
    expect(matrix[0][5]).toBe(2); // 正式观测 失败
    expect(matrix[0][6]).toBe(2); // 全局关联 失败
    expect(matrix[0][8]).toBe(2); // 连续漏检（streak>0）
    expect(matrix[0][0]).toBe(1); // 期望区域 通过
  });

  it("treats missing fields as not triggered", () => {
    const { matrix } = buildHeatmapMatrix([row({ projection_status: null, binding_visibility: null as unknown as string })]);
    expect(matrix[0][7]).toBe(0); // 绑定可见性 null → 未触发
  });

  it("merges two views per tick: pass wins, all-fail is fail", () => {
    const passed = row({ view_id: "cam_1", position_present: true });
    const failed = row({ view_id: "cam_2", position_present: false });
    const bothFailed = [row({ view_id: "cam_1", position_present: false }), row({ view_id: "cam_2", position_present: false })];
    expect(buildHeatmapMatrix([passed, failed]).matrix[0][3]).toBe(1);
    expect(buildHeatmapMatrix(bothFailed).matrix[0][3]).toBe(2);
  });

  it("returns empty ticks for no rows", () => {
    const { ticks, matrix } = buildHeatmapMatrix([]);
    expect(ticks).toEqual([]);
    expect(matrix).toEqual([]);
  });
});
