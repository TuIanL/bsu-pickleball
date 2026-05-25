## Context

Completed analysis jobs can already expose projected player positions as frame-level records containing `track_id`, timestamp/frame, court coordinates, and confidence. The current analysis details court plan does not present that data in a user-readable way: it draws one path from the first available track and a limited set of points that can mix many tracks without labels.

Real outputs can contain tens of thousands of projected points and hundreds of raw tracker IDs. Those IDs are technical continuity labels from computer vision tracking, not guaranteed named player identities. The UI therefore needs to explain what the visualization means while staying honest about identity uncertainty and tracker fragmentation.

## Goals / Non-Goals

**Goals:**

- Make the projected court plan understandable without requiring users to know the backend data schema.
- Show which plotted marks belong to which raw movement track.
- Let users focus on selected or likely primary tracks instead of seeing an unreadable cloud of all points.
- Preserve the existing analysis details route and current backend payload shape for the first implementation.
- Keep rendering responsive on large result files.

**Non-Goals:**

- Do not solve named-player identification or jersey/person recognition.
- Do not guarantee that one raw `track_id` represents one real person for an entire match.
- Do not add a backend migration or new required API field for this change.
- Do not redesign unrelated report pages, video overlays, or task management flows.

## Decisions

1. Derive display metadata on the frontend from existing projected track records.

   The details page can group records by `track_id`, compute point count, time span, confidence range, court bounds, and a persistence score. This avoids blocking the usability fix on backend schema work. A future backend can still provide richer role labels or merged identity tracks without changing the page concept.

2. Use display labels instead of treating raw `track_id` as a human identity.

   The UI should label tracks as `轨迹 1`, `轨迹 2`, etc. and optionally expose the raw ID as diagnostic context. This matches the current tracker behavior, where IDs can fragment after occlusion, missed detections, or reassociation.

3. Render distinct track groups with selection and summary controls.

   Each visible track gets a stable color and legend entry. The court should support at least all visible primary tracks and single-track inspection, with clear start/latest markers. Short/noisy fragments should be hideable by default or through an explicit filter so the map does not become a dense cloud.

4. Explain point semantics near the visualization.

   The court plan should state that a point is the estimated player footpoint projected from image space into the standard 20 ft by 44 ft court coordinate system. Inspection should show timestamp, frame, coordinates, confidence, and track label so users can connect visual marks to analysis evidence.

5. Downsample for rendering, not for summaries.

   Summaries should be computed from all available records, but drawing can cap or sample points per track to protect browser performance. The UI should prefer preserving start/end/current markers and representative path shape over plotting every raw point.

## Risks / Trade-offs

- Raw tracker IDs can fragment or swap after missed detections -> The UI labels them as movement tracks, includes uncertainty copy, and provides filters rather than claiming named-player identity.
- Large jobs can produce too many points to draw smoothly -> The renderer caps/downsamples plotted points while keeping full-data summary counts.
- Color-only distinction can be inaccessible -> Track labels, marker shapes, and legend text accompany color.
- Deriving primary tracks from frontend heuristics can be imperfect -> The page presents them as likely/persistent tracks and keeps a way to inspect all tracks.
- Users may confuse projected footpoints with ball landing or shot contact points -> The visualization text and point inspection explicitly define point meaning.
