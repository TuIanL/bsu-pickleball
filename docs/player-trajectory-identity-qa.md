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

## Court-Aware Player Selection

- Review `player_selection.json` before trusting a difficult multi-court clip.
- Target players should have high `target_court_score` and be selected as `target_player`.
- Adjacent-court players may move actively; they should still be rejected with `neighbor_court_player` or low target-court membership.
- Do not treat missing target-court players as a reason to fill the roster with lower-scoring adjacent-court tracks.
- If `selection_mode` is `fallback`, confirm the fallback reason and verify the rule selector still produced reasonable eligible tracks.

## Training Sample Labels

- Exported `player_selection_training_samples.json` samples start as `uncertain`.
- Label target-court players as `target_player`.
- Label active players from adjacent courts as `neighbor_court_player`.
- Label non-participating people as `spectator`.
- Keep ambiguous or occluded cases as `uncertain` until video review resolves them.

## Acceptance Targets

- First pass: reduce raw dozens of source tracks to four to six reviewable identities, with the final metric artifact capped at four players.
- Second pass: maintain four stable player trajectories with visibly reduced ID switches and no obvious distance or heatmap jumps.
- Multi-court clips: adjacent-court moving players should not appear in final player trajectories for the target court.
