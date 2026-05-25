## Why

Completed job report pages currently wait for raw pipeline results and large overlay artifacts before rendering, even when the requested page only needs the lightweight report payload. This makes locally generated reports appear to be "still loading" after analysis is complete, especially when pose overlay artifacts are hundreds of megabytes.

## What Changes

- Make job-specific report detail pages render from the job summary and report payload without blocking on raw result or overlay artifact downloads.
- Keep completed visual analysis pages able to use raw result, tracking overlay, and pose overlay data, but load heavyweight overlay artifacts independently from the lightweight report shell.
- Add explicit loading, unavailable, and degraded overlay states so the video workspace remains usable while detection or pose artifacts are still downloading or fail to load.
- Preserve demo/sample report behavior and completed-job routing while making loading copy reflect whether the app is reading a report or loading visual overlay data.
- Avoid changing the backend analysis pipeline output format in this change; the focus is frontend loading boundaries and user-facing states.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `report-detail-pages`: Job-specific reports must render once lightweight job/report data is available and must not wait for raw algorithm results or overlay artifacts that are not required by the selected report.
- `visual-analysis-workspace`: Completed real-job video workspaces must treat detection and pose overlays as independently loaded visual layers, keeping the source video and report/status rail usable while heavy artifacts load or degrade.

## Impact

- Frontend data-loading structure in `src/App.tsx`, especially `useAnalysisReport`, `ReportPage`, and `VisionPage`.
- Analysis API client usage in `src/services/analysisClient.ts`, with likely separation between report/job fetches and raw result/overlay fetches.
- Video overlay UI state handling in `src/components/platform/VideoAnalysisCard.tsx` and related playback helpers.
- Existing backend endpoints can remain compatible, but local testing should cover large artifacts such as `pose_overlay.json` so regressions are visible.
