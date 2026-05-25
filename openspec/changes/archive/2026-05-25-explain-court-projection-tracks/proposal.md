## Why

The current projected 2D court visualization shows paths and points without explaining what they represent, which track they belong to, or how reliable the identities are. Users need the court projection to be coach-readable: it should make clear that the marks are projected player footpoints over time, not ball contacts, shot landing points, or confirmed named players.

## What Changes

- Add a track explanation layer to the analysis details court plan that defines each plotted point as a projected player footpoint in standard court coordinates.
- Render projected movement by distinguishable track groups with legend labels, colors, and start/latest markers instead of a single ambiguous line plus mixed points.
- Provide track summaries and filters so users can select one track, view likely primary tracks, and hide short/noisy track fragments.
- Add point inspection context for timestamp, frame, court coordinate, confidence, and track label.
- Add honest uncertainty copy for raw tracker identities, including the fact that `track_id` can be fragmented when detections are lost or reassigned.
- Keep the existing details route and backend result contract; derive display metadata from the existing projected track records where possible.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `analysis-details-page`: The projected court plan must explain projected player movement tracks, distinguish track groups, and expose enough inspection/filtering context for users to understand what the points and paths mean.

## Impact

- Affected frontend areas include the analysis details page, the standard court plan visualization, and any helper logic used to summarize projected track records.
- No new backend API is required for the first implementation because the current projected records already include `track_id`, frame/time, court coordinates, and confidence.
- Rendering needs basic performance safeguards because real jobs can produce many projected points and many fragmented tracker IDs.
