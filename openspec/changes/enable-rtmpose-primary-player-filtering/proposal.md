## Why

Recent real-video analysis can produce player boxes without skeletons because RTMPose is still disabled by default, and the current overlay subject filter removes valid match players whenever their projected footpoints fall outside the court tolerance. Pickleball players naturally step outside the lines, so the presentation layer needs a player-selection strategy based on detection quality and track prominence rather than a strict in-bounds rule.

## What Changes

- Enable RTMPose for real calibrated video jobs when the RTMPose runtime and model assets are configured, while preserving explicit unavailable states when assets or dependencies are missing.
- Replace strict court-in-bounds overlay filtering with confidence-based primary-player filtering for browser-facing person boxes and RTMPose subjects.
- Score tracked people over time using detection confidence, track persistence, frame-level ranking, and reasonable size/continuity signals so the overlay keeps the main match participants and drops low-confidence or incidental people.
- Keep court projection available for movement metrics and diagnostics, but stop using normal line-out movement as the main reason to hide boxes or skeletons.
- Preserve a broad court-distance sanity check only for obvious non-match detections when it helps reject spectators far from the playable scene.
- Expose clear artifact details for how many raw detections were found, how many primary-player boxes were kept, and whether RTMPose generated skeletons.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `player-tracking-engine`: renderable detection overlay subjects are selected by primary-player confidence and track quality rather than strict court-bound footpoint filtering.
- `pose-estimation-engine`: RTMPose is enabled for configured real-video jobs and receives the same primary-player subject set used by detection overlays.
- `visual-analysis-workspace`: real-video overlay status must distinguish unavailable RTMPose configuration from successful analysis with zero selected primary players.

## Impact

- Backend: `backend/app/core/config.py`, `backend/app/services/analysis_pipeline.py`, tracking schemas or helpers if primary-player selection metadata is persisted.
- Vision modules: primary-player scoring/filtering logic near the tracking pipeline, plus optional court-distance diagnostics without hard line-bound rejection.
- Frontend: overlay status/detail copy in `src/components/platform/VideoAnalysisCard.tsx` and report adaptation if artifact detail strings change.
- Documentation: backend RTMPose setup and the new confidence/primary-player filtering configuration.
- Tests: regression coverage for RTMPose activation, primary-player filtering, spectator/low-confidence rejection, and players stepping outside court lines remaining visible.
