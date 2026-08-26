import { describe, expect, it } from "vitest";
import fixture from "../test/fixtures/shot-rally-events.v1.json";
import type { ShotRallyEventsArtifact } from "../types/shotRallyEvents";
import { buildRallyShotTimelineModel, shotTimelineTimestampMs } from "./rallyShotTimeline";

const artifact = fixture as unknown as ShotRallyEventsArtifact;

describe("rally shot timeline model", () => {
  it("groups canonical shots by rally, deduplicates shot ids, and calculates descriptive summaries", () => {
    const duplicate = { ...artifact.shots[0], stage: "rally_shot" as const };
    const model = buildRallyShotTimelineModel({ ...artifact, shots: [...artifact.shots, duplicate] });

    expect(model.mode).toBe("rallies");
    expect(model.rows.map((row) => row.id)).toEqual(["rally-001", "rally-002"]);
    expect(model.summary.shotCount).toBe(5);
    expect(model.summary.rallyCount).toBe(2);
    expect(model.summary.averageShotsPerRally).toBe(2.5);
    expect(model.summary.stageCounts).toMatchObject({ serve: 2, return: 1, third: 1, rally_shot: 1 });
    expect(model.summary.unassignedCount).toBe(1);
  });

  it("falls back to a chronological row without inventing rally boundaries or ordinals", () => {
    const noBoundary: ShotRallyEventsArtifact = {
      ...artifact,
      rallies: [],
      shots: artifact.shots.map((shot) => ({ ...shot, rally_id: null, ordinal_in_rally: null })),
      diagnostics: { ...artifact.diagnostics, rally_boundary_status: "unavailable" },
    };
    const model = buildRallyShotTimelineModel(noBoundary);

    expect(model.mode).toBe("chronological");
    expect(model.hasAuthoritativeRallyBoundary).toBe(false);
    expect(model.rows).toHaveLength(1);
    expect(model.rows[0].events).toHaveLength(5);
    expect(model.rows[0].events.every((event) => event.ordinalInRally === null)).toBe(true);
    expect(model.summary.rallyCount).toBe(0);
    expect(model.summary.averageShotsPerRally).toBeNull();
  });

  it("preserves ambiguous ownership and evidence availability", () => {
    const model = buildRallyShotTimelineModel(artifact);
    const ambiguous = model.events.find((event) => event.shotId === "shot-004");
    const confirmed = model.events.find((event) => event.shotId === "shot-001");

    expect(ambiguous).toMatchObject({
      playerId: null,
      playerLabel: "击球者不明",
      ownershipLabel: "击球者不明",
      canSeek: false,
      qualityBand: "none",
    });
    expect(confirmed).toMatchObject({
      playerId: "Player_1",
      playerLabel: "P1",
      canSeek: true,
      evidenceStartMs: 1100,
      evidenceEndMs: 1500,
    });
  });

  it("uses contact, then start, then end as the event time", () => {
    expect(shotTimelineTimestampMs({ contact_ms: 12, start_ms: 10, end_ms: 20 })).toBe(12);
    expect(shotTimelineTimestampMs({ contact_ms: null, start_ms: 10, end_ms: 20 })).toBe(10);
    expect(shotTimelineTimestampMs({ contact_ms: null, start_ms: Number.NaN, end_ms: 20 })).toBe(20);
  });

  it("returns an empty model for a non-available artifact", () => {
    const unavailable = { ...artifact, status: "unavailable" as const, detail: "缺少 reconstructed trajectory" };
    const model = buildRallyShotTimelineModel(unavailable);

    expect(model.mode).toBe("empty");
    expect(model.events).toEqual([]);
    expect(model.detail).toContain("缺少 reconstructed trajectory");
  });
});
