# Player Trajectory Identity QA

Use this checklist when validating stable doubles player identities on real match clips.

## Units

- Final player trajectory artifacts use meters as the canonical court unit.
- Court metadata must report `court_unit: "m"`, canonical dimensions `13.41 m x 6.10 m`, and imperial reference dimensions `44 ft x 20 ft`.
- Legacy tracking and overlay artifacts can still expose source `track_id` data; player trajectory JSON/CSV is the canonical player-level output.

## Core Metrics

- Final player count: expected at most four `Player_x` trajectories for doubles.
- Source track fragmentation: count distinct source `track_id` values in each player's `history_track_ids`.
- ID switch review: inspect diagnostics where a source track is assigned or reconnected to a player.
- Reconnect success: count `reconnected` diagnostics after short missing intervals.
- Average lost duration: compare `lost` diagnostics against later `reconnected` or `assigned` events.
- Unmatched tracks: review `unmatched` and `filtered` diagnostics for spectators or bad projections.

## Visual Review

- Overlay labels should show stable and temporary identities together when available, for example `P1 / T12`.
- Player colors in debug views should be keyed by `player_id`, not by temporary `track_id`.
- Interpolated trajectory points must be visually distinguishable from detector-backed points.

## Acceptance Targets

- First pass: reduce raw dozens of source tracks to four to six reviewable identities, with the final metric artifact capped at four players.
- Second pass: maintain four stable player trajectories with visibly reduced ID switches and no obvious distance or heatmap jumps.
