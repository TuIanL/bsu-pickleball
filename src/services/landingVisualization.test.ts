import { describe, expect, it } from "vitest";
import { ALL_LANDING_FILTERS, filterLandings, groupLandingStatuses, zone12Stats } from "./landingVisualization";
import type { ShotLanding } from "../types/shotLandings";

const landing = (shot_id: string, overrides: Partial<ShotLanding> = {}): ShotLanding => ({
  landing_id: `landing-${shot_id}`, shot_id, landing_status: "available", court_location: "inside_court",
  target_relation: "target_half", orientation_transform: "identity", canonicalization_basis: "hitter_position_at_contact",
  source_artifacts: [], diagnostics: [], ...overrides,
});

describe("landing visualization adapter", () => {
  const rows = [
    landing("s1", { hitter_player_id: "Player_1", rally_id: "r1", shot_stage: "third", bounce_confidence: .9, zone_12: "VD-R" }),
    landing("s2", { hitter_player_id: "Player_2", rally_id: "r1", bounce_confidence: .4, zone_12: "VD-R" }),
    landing("s3", { landing_status: "no_bounce_before_next_contact", bounce_confidence: null }),
  ];

  it("applies every filter to the same collection", () => {
    expect(filterLandings(rows, { ...ALL_LANDING_FILTERS, player: "Player_1", rally: "r1", stage: "third", minConfidence: .8 }).map((item) => item.shot_id)).toEqual(["s1"]);
  });

  it("uses only zoned landings as the zone denominator", () => {
    const stats = zone12Stats(rows);
    expect(stats.denominator).toBe(2);
    expect(stats.counts["VD-R"]).toBe(2);
    expect(stats.ratio("VD-R")).toBe(1);
  });

  it("keeps non-spatial statuses visible", () => {
    expect(groupLandingStatuses(rows).no_bounce_before_next_contact).toBe(1);
  });
});
