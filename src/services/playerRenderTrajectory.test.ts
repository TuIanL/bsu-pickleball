import { describe, expect, it, vi, beforeEach } from "vitest";
import { normalizePlayerRenderTrajectory } from "./playerRenderTrajectory";
import { getPlayerRenderTrajectory } from "./analysisClient";
import v2Fixture from "../test/fixtures/player-render-trajectory.v2.json";
import { DEFAULT_COURT_VISUAL_THEME_V1 } from "../types/report";
import type { RawPlayerRenderTrajectoryV1, RawPlayerRenderTrajectoryV2 } from "../types/report";

describe("normalizePlayerRenderTrajectory", () => {
  it("parses v2 fixture and produces NormalizedRenderFrame with all required fields", () => {
    const raw = v2Fixture as unknown as RawPlayerRenderTrajectoryV2;
    const normalized = normalizePlayerRenderTrajectory(raw);

    expect(normalized.players).toHaveLength(2);
    expect(normalized.segments).toHaveLength(3);
    expect(normalized.samples.length).toBeGreaterThan(0);

    for (const s of normalized.samples) {
      expect(typeof s.render_slot).toBe("string");
      expect(s.render_slot).toBeTruthy();
      expect(typeof s.segment_id).toBe("string");
      expect(typeof s.identity_epoch).toBe("number");
      expect(["near", "far", "unknown"]).toContain(s.side);
    }
  });

  it("assigns render_slot and byPlayer/bySegment indexes", () => {
    const raw = v2Fixture as unknown as RawPlayerRenderTrajectoryV2;
    const normalized = normalizePlayerRenderTrajectory(raw);

    expect(Object.keys(normalized.byPlayer)).toEqual(["Player_1", "Player_2"]);
    expect(Object.keys(normalized.bySegment).sort()).toEqual([
      "Player_1:e0:s0",
      "Player_2:e0:s0",
    ]);
    expect(normalized.byPlayer["Player_1"].length).toBeGreaterThan(0);
  });
});

describe("v1 fallback", () => {
  it("normalizes v1 artifact without render_slot by assigning temporary slots", () => {
    const v1: RawPlayerRenderTrajectoryV1 = {
      samples: [
        { frame_index: 0, timestamp_seconds: 0, x_ft: 5, y_ft: 10, source: "detected", confidence: 0.9, player_id: "Player_1" },
        { frame_index: 0, timestamp_seconds: 0, x_ft: 10, y_ft: 20, source: "detected", confidence: 0.85, player_id: "Player_2" },
        { frame_index: 1, timestamp_seconds: 0.033, x_ft: 6, y_ft: 11, source: "detected", confidence: 0.88, player_id: "Player_1" },
      ],
    };
    const normalized = normalizePlayerRenderTrajectory(v1);

    expect(normalized.samples.length).toBe(3);
    const p1Slots = normalized.samples.filter((s) => s.player_id === "Player_1").map((s) => s.render_slot);
    const p2Slots = normalized.samples.filter((s) => s.player_id === "Player_2").map((s) => s.render_slot);

    expect(p1Slots.every((s) => s === "slot_1")).toBe(true);
    expect(p2Slots.every((s) => s === "slot_2")).toBe(true);
  });

  it("derives temporary segments for v1 artifact with time gaps", () => {
    const v1: RawPlayerRenderTrajectoryV1 = {
      samples: [
        { frame_index: 0, timestamp_seconds: 0, x_ft: 0, y_ft: 0, source: "detected", confidence: 0.9, player_id: "Player_1" },
        { frame_index: 1, timestamp_seconds: 0.033, x_ft: 1, y_ft: 1, source: "detected", confidence: 0.85, player_id: "Player_1" },
        { frame_index: 30, timestamp_seconds: 1.0, x_ft: 5, y_ft: 5, source: "detected", confidence: 0.8, player_id: "Player_1" },
        { frame_index: 31, timestamp_seconds: 1.033, x_ft: 6, y_ft: 6, source: "detected", confidence: 0.85, player_id: "Player_1" },
      ],
    };
    const normalized = normalizePlayerRenderTrajectory(v1);

    expect(normalized.segments.length).toBe(2);
    expect(normalized.segments[0].segment_id).toBe("legacy:Player_1:e0:s0");
    expect(normalized.segments[1].segment_id).toBe("legacy:Player_1:e0:s1");
    expect(normalized.segments[0].break_before).toBe("start");
    expect(normalized.segments[1].break_before).toBe("visible_gap");
  });

  it("falls back to DEFAULT_COURT_VISUAL_THEME_V1 when v1 has no style_profile", () => {
    const v1: RawPlayerRenderTrajectoryV1 = {
      samples: [
        { frame_index: 0, timestamp_seconds: 0, x_ft: 5, y_ft: 10, source: "detected", confidence: 0.9, player_id: "Player_1" },
      ],
    };
    const normalized = normalizePlayerRenderTrajectory(v1);
    expect(normalized.style_profile).toEqual(DEFAULT_COURT_VISUAL_THEME_V1);
    expect(normalized.segmentation_profile).toBeNull();
  });
});

describe("getPlayerRenderTrajectory", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns null on 404", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 404 }),
    );
    const result = await getPlayerRenderTrajectory("nonexistent-job");
    expect(result).toBeNull();
  });

  it("throws on 500", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 500 }),
    );
    await expect(getPlayerRenderTrajectory("failing-job")).rejects.toThrow();
  });
});

describe("contract: style_profile consistency", () => {
  it("DEFAULT_COURT_VISUAL_THEME_V1 matches backend fixture style_profile", () => {
    const fixtureStyle = (v2Fixture as any).style_profile;

    expect(DEFAULT_COURT_VISUAL_THEME_V1.version).toBe(fixtureStyle.version);
    expect(DEFAULT_COURT_VISUAL_THEME_V1.players.slot_1).toBe(fixtureStyle.players.slot_1);
    expect(DEFAULT_COURT_VISUAL_THEME_V1.players.slot_2).toBe(fixtureStyle.players.slot_2);
    expect(DEFAULT_COURT_VISUAL_THEME_V1.players.slot_3).toBe(fixtureStyle.players.slot_3);
    expect(DEFAULT_COURT_VISUAL_THEME_V1.players.slot_4).toBe(fixtureStyle.players.slot_4);
    expect(DEFAULT_COURT_VISUAL_THEME_V1.ball).toBe(fixtureStyle.ball);
    expect(DEFAULT_COURT_VISUAL_THEME_V1.player_trail_seconds).toBe(fixtureStyle.player_trail_seconds);
  });

  it("v2 fixture render_slot survives normalization unchanged", () => {
    const raw = v2Fixture as unknown as RawPlayerRenderTrajectoryV2;
    const normalized = normalizePlayerRenderTrajectory(raw);

    for (const p of raw.players) {
      const playerSamples = normalized.samples.filter((s) => s.player_id === p.player_id);
      for (const s of playerSamples) {
        expect(s.render_slot).toBe(p.render_slot);
      }
    }
  });
});
