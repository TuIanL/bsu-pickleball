## 1. Data Preparation

- [x] 1.1 Inspect the current analysis result type and `StandardCourtPlan` data flow for projected track records.
- [x] 1.2 Add a frontend helper that groups projected positions by `track_id` and derives track summaries from the complete available data.
- [x] 1.3 Compute stable display labels, colors, point counts, time ranges, confidence context, and persistence ordering for track summaries.
- [x] 1.4 Add rendering caps or sampling helpers that preserve start/latest points while limiting drawn points per track.

## 2. Court Visualization

- [x] 2.1 Update the court plan to render distinguishable per-track paths and points instead of a single first-track path with mixed unlabeled points.
- [x] 2.2 Add start and latest-position markers for each visible track.
- [x] 2.3 Add selected-track highlighting and de-emphasize unselected tracks while preserving a reset or all-tracks view.
- [x] 2.4 Add empty, unavailable, or no-calibration states that explain why projected positions cannot be shown.

## 3. Track Controls and Explanation

- [x] 3.1 Add a track legend or side panel showing visible track labels, colors, point counts, time ranges, and confidence or persistence context.
- [x] 3.2 Add controls for selecting a track and hiding or de-emphasizing short/noisy track fragments.
- [x] 3.3 Add concise explanatory copy that defines points as projected player footpoints in standard court coordinates.
- [x] 3.4 Add identity uncertainty copy that explains raw tracker labels are movement tracks, not guaranteed named players.
- [x] 3.5 Add hover, focus, or click inspection for representative points with track label, timestamp or frame, court coordinate, and confidence.

## 4. Verification

- [x] 4.1 Add focused unit coverage for the track grouping, summary, ordering, and sampling helpers where the project test setup supports it.
- [x] 4.2 Verify a completed sample job with many projected points remains responsive and visually readable.
- [x] 4.3 Verify narrow and desktop layouts so the court, legend, controls, and inspection text do not overlap.
- [x] 4.4 Run the relevant build or test command and record any remaining limitations.
