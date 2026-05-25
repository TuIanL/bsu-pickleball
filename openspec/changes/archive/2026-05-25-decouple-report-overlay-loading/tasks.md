## 1. Data Loading Boundaries

- [x] 1.1 Inspect current `useAnalysisReport` call sites and identify which pages need only job/report data versus raw result and overlays.
- [x] 1.2 Add a lightweight job-report loading path that fetches `getAnalysisJob` and `getAnalysisReport` without calling `getAnalysisResult`, `getTrackingOverlay`, or `getPoseOverlay`.
- [x] 1.3 Add or refactor a visual-result loading path that can expose job/report/result state before overlay artifact requests finish.
- [x] 1.4 Ensure hook cleanup prevents stale async updates when users navigate between job routes while result or overlay requests are still pending.

## 2. Report Detail Pages

- [x] 2.1 Update `ReportPage` to consume the lightweight job-report loading path.
- [x] 2.2 Preserve existing completed, queued/processing, failed, canceled, not-found, and demo/sample report states.
- [x] 2.3 Update loading and unavailable copy so report routes describe report data loading rather than visual overlay loading.
- [x] 2.4 Verify a completed job report route renders without waiting for `result`, `tracking-overlay`, or `pose-overlay` requests.

## 3. Visual Analysis Workspace

- [x] 3.1 Update `VisionPage` to render the completed-job video shell, status rail, and report actions once job/report and required result metadata are available.
- [x] 3.2 Load tracking overlay and pose overlay artifacts as independent layer states after the base completed-job shell can render.
- [x] 3.3 Represent overlay layer states as loading, available, unavailable, skipped, or failed without turning layer failures into full-page errors.
- [x] 3.4 Keep source video playback, report navigation, and available overlay layers usable while another overlay artifact is still downloading or parsing.

## 4. UI State Integration

- [x] 4.1 Update `AnalysisStatusRail` or adjacent status components to communicate layer-specific loading and degraded states.
- [x] 4.2 Update `VideoAnalysisCard` props or derived state so missing overlays, loading overlays, and failed overlays are visually distinct from demo overlays.
- [x] 4.3 Ensure fullscreen and inline playback still receive the same available overlay data once each layer finishes loading.
- [x] 4.4 Confirm the page does not flash unrelated demo player markers while real overlay artifacts are unavailable or pending.

## 5. Verification

- [x] 5.1 Run frontend typecheck/build to catch hook state and prop type regressions.
- [x] 5.2 Test a completed report route with a known large `pose_overlay.json` and confirm the report content renders quickly from the lightweight payload.
- [x] 5.3 Test the completed visual analysis route for the same job and confirm the base video/status shell appears before or independently of the pose overlay.
- [x] 5.4 Test overlay failure or missing-artifact cases for tracking and pose layers and confirm the page remains usable.
- [x] 5.5 Use browser verification for desktop and narrow viewports to confirm loading/degraded overlay labels do not overlap video controls or report actions.
