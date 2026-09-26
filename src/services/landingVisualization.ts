import type { LandingStatus, ShotLanding, ShotLandingsArtifact } from "../types/shotLandings";

export interface LandingFilters {
  player: string;
  rally: string;
  stage: string;
  minConfidence: number;
}

export const ALL_LANDING_FILTERS: LandingFilters = { player: "all", rally: "all", stage: "all", minConfidence: 0 };

export function filterLandings(items: ShotLanding[], filters: LandingFilters): ShotLanding[] {
  return items.filter((item) =>
    (filters.player === "all" || item.hitter_player_id === filters.player)
    && (filters.rally === "all" || item.rally_id === filters.rally)
    && (filters.stage === "all" || item.shot_stage === filters.stage)
    && (item.bounce_confidence ?? 0) >= filters.minConfidence,
  );
}

export function groupLandingStatuses(items: ShotLanding[]): Record<LandingStatus, number> {
  const result: Record<LandingStatus, number> = {
    available: 0, no_bounce_before_next_contact: 0, bounce_without_court_coordinate: 0,
    ambiguous_bounce: 0, unavailable: 0,
  };
  for (const item of items) result[item.landing_status] += 1;
  return result;
}

export function zone12Stats(items: ShotLanding[]) {
  const eligible = items.filter((item) => item.zone_12);
  const counts: Record<string, number> = {};
  for (const item of eligible) counts[item.zone_12!] = (counts[item.zone_12!] ?? 0) + 1;
  return { denominator: eligible.length, counts, ratio: (zone: string) => eligible.length ? (counts[zone] ?? 0) / eligible.length : 0 };
}

export function landingSummary(artifact: ShotLandingsArtifact, items: ShotLanding[]) {
  return {
    displayed: items.length,
    total: artifact.summary.shot_count,
    measurable: items.filter((item) => item.landing_status === "available").length,
    zoned: items.filter((item) => item.zone_12).length,
  };
}
