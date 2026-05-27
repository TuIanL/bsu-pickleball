## Context

The backend already has a modular player tracking path: YOLO-style person detections, a replaceable multi-object tracker contract, footpoint estimation, homography projection, primary-player selection, overlay artifact generation, and movement metrics. The current tracker is a simple IOU implementation that can preserve IDs for short local motion, but it does not solve full match-level identity stability. When detections are lost during occlusion, out-of-frame movement, or player crossings, downstream outputs can accumulate many `track_id` fragments for only four real doubles players.

The new design adds a stable identity layer after court projection. The pipeline will continue to treat `detection`, `track_id`, and `player_id` as separate concepts:

```text
Detection        temporary model observation for one frame
track_id         tracker-maintained short-term target identity
player_id        match-level real player identity, capped at four for doubles
```

Court coordinates used by identity matching and final artifacts will be canonical metric coordinates. The standard pickleball court is 13.41 m long by 6.10 m wide, with imperial reference dimensions of 44 ft by 20 ft documented in metadata. Existing compatibility fields may be retained during migration only when unit metadata is explicit.

## Goals / Non-Goals

**Goals:**

- Reduce track fragmentation by mapping multiple temporary `track_id` values onto stable `Player_1` through `Player_4` identities.
- Use metric court coordinates for matching thresholds, speed filters, interpolation, final JSON/CSV exports, and QA metrics.
- Preserve diagnostic traceability from final `player_id` samples back to source `track_id`, bbox, confidence, and projection data.
- Repair short missing intervals with interpolation while marking synthetic points distinctly from detector-backed observations.
- Keep the tracker implementation replaceable so the first implementation can use existing IOU tests while production can move to BoT-SORT or ByteTrack.

**Non-Goals:**

- Retraining YOLO or changing the person detector model quality.
- Building deep ReID as a first requirement; simple appearance features can be added after metric-position matching works.
- Solving multi-camera fusion, tactical analysis, or pose-based identity recovery in this change.
- Guaranteeing mathematically perfect identity recovery for long out-of-frame gaps; the goal is practical stability and transparent diagnostics.

## Decisions

### Add identity management after projection

The Player Identity Manager consumes projected observations rather than raw image boxes. This makes association less sensitive to camera perspective and aligns with movement metrics.

```text
Frame
  ↓
Person Detection
  ↓
Multi-object Tracker
  ↓
Footpoint + Homography Projection
  ↓
Primary Player Filtering
  ↓
Player Identity Manager
  ↓
Trajectory Repair + Export
```

Alternative considered: assign identities inside the tracker. That would blur temporary tracker state with match-level player identity and make BoT-SORT / ByteTrack replacement harder.

### Use metric coordinates as canonical

Identity matching, speed limits, interpolation, and exported player trajectories will use meters. Court metadata will include both:

```text
canonical: width=6.10 m, length=13.41 m
reference: width=20 ft, length=44 ft
conversion: 1 ft = 0.3048 m
```

If existing projection helpers still produce 20-by-44 court coordinates during migration, the identity layer must convert them to meters before applying thresholds. New fields and artifacts must include unit metadata such as `court_unit: "m"` so downstream metrics do not infer units from field names.

Alternative considered: keep feet because current tests use 20 by 44. That avoids migration work but makes the new identity thresholds less intuitive for the team and conflicts with the requested canonical unit.

### Keep `track_id` diagnostic history

Every player state stores current and historical source track IDs. Final samples include `player_id`, `track_id`, bbox, image footpoint, metric court point, confidence, status, and interpolation marker. Assignment logs should include frame, source track, target player, score, and dominant reason.

Alternative considered: collapse track IDs after assignment. That would make final artifacts cleaner but remove the evidence needed to debug ID switches.

### Cap player creation at match participant count

For doubles, the identity manager creates no more than four players. Once four players exist, unmatched tracks must either reconnect to the best existing player, remain unmatched for diagnostics, or be dropped as incidental detections. This complements `PrimaryPlayerSelector`, which filters each frame to likely match participants; it does not replace identity management.

Alternative considered: export all tracks and select top four later. That preserves raw data but still exposes fragmented trajectories to metrics.

### Start with position and motion matching, then add appearance

The first implementation should score candidates with metric position distance and motion continuity. Color histogram appearance can be added as an optional feature once baseline assignment and tests are stable.

Initial threshold examples in metric units:

- reconnect distance: 0.6 m to 1.0 m for very short gaps, expanding up to about 2.5 m for 1-3 second gaps
- lost buffer: 90 frames at 30 fps
- inactive buffer: 180 frames at 30 fps
- maximum plausible player speed: 7.0 m/s, with imperial reference about 23.0 ft/s
- court bounds with tolerance: x/y ranges based on 6.10 m by 13.41 m plus a configurable buffer

Alternative considered: require BoT-SORT ReID before identity management. That may improve recovery but adds dependency and model complexity before the output contract is stable.

## Risks / Trade-offs

- Unit migration can silently corrupt metrics if feet and meters mix. -> Add explicit unit metadata, conversion helpers, tests for court dimensions and speed thresholds, and avoid applying identity thresholds to unlabelled coordinates.
- A hard four-player cap can misassign spectators if primary filtering is weak. -> Run primary-player filtering before identity assignment, keep unmatched diagnostics, and require confidence/track quality gates.
- Position-only reconnection can fail when players cross or swap sides. -> Use motion score, short gap limits, assignment logs, and optional appearance score as a second phase.
- Large `track_buffer` values can reconnect the wrong player. -> Keep tracker buffer configurable and let the identity manager make final player decisions with court-space sanity checks.
- Interpolation can make synthetic points look real. -> Mark every repaired sample with `is_interpolated=true` and a `tracking_status` distinct from detected samples.
