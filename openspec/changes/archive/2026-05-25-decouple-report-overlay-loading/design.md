## Context

Job-specific report routes currently call the same report-loading hook as the visual analysis workspace. That hook requests the job summary, report payload, raw pipeline result, tracking overlay, and pose overlay before it publishes any loaded state to the page.

For small demo data this feels harmless, but completed real jobs can produce very large overlay files. In the observed local job, the report payload was only about 8 KB and loaded in milliseconds, while the pose overlay artifact was over 100 MB over the API and over 200 MB on disk. A report page that only needs movement or diagnosis content should not wait for that artifact.

The backend already exposes compatible endpoints for job summaries, report payloads, raw results, and artifacts. This change can be implemented by changing frontend loading boundaries first, without altering pipeline output or persisted artifact formats.

## Goals / Non-Goals

**Goals:**

- Let job-specific report pages render as soon as their lightweight job summary and report payload are available.
- Keep raw pipeline results and overlays available to the visual analysis workspace without blocking the initial report shell.
- Give users honest loading copy: report pages should say they are loading report data; video pages should say when overlays are loading.
- Preserve demo/sample routes and existing completed-job routes.
- Keep failures isolated so a failed or slow pose overlay does not prevent source video, report navigation, or status metadata from rendering.

**Non-Goals:**

- Change the backend analysis pipeline, RTMPose generation, artifact file format, or persisted storage layout.
- Add pagination, streaming, compression, or chunked overlay APIs in this change.
- Redesign report content, metrics, model inference, or calibration behavior.
- Remove existing raw result or overlay endpoints.

## Decisions

### Decision: Split lightweight report loading from visual artifact loading

Introduce separate frontend loading boundaries for:

- lightweight job report state: job summary plus report payload
- raw result state: pipeline result and source video reference
- overlay state: tracking and pose artifacts

Report detail pages should consume only the lightweight report state unless a specific report module later proves it needs raw result data.

Alternative considered: keep one hook and add flags such as `includeOverlays: false`. This can work if the implementation stays small, but the important boundary is semantic rather than just boolean. The report page contract should remain visibly lightweight, while the visual workspace contract can own overlays.

### Decision: Render the visual workspace shell before overlays finish

The completed visual analysis page should render the source video, job metadata, report actions, and overlay status rail once job/report/result information is available. Tracking and pose overlays should update independently when their artifact fetches complete.

Alternative considered: keep blocking visual workspace rendering until all overlays finish so the first paint is complete. That makes large real jobs feel broken and hides useful actions while the user waits. Independent layer loading gives a more honest and usable experience.

### Decision: Treat overlay failures as degraded layer states

Tracking and pose artifact requests should be allowed to fail independently and should map to layer-specific unavailable or failed states. A failed pose overlay should not erase detection boxes, source video, report navigation, or completed job metadata.

Alternative considered: surface any overlay fetch failure as a full-page error. That is appropriate for missing job/report data, but too severe for optional visual layers whose absence already has status labels.

### Decision: Keep backend endpoint compatibility for this change

The first implementation should continue using the existing job, report, result, and artifact endpoints. Large-artifact optimization can be proposed later if the product needs faster first skeleton paint, compressed transport, frame-window fetching, or binary overlay formats.

Alternative considered: immediately introduce chunked overlay APIs. That is likely the long-term direction, but it expands the change into backend API design and migration before fixing the immediate report-page blocking problem.

## Risks / Trade-offs

- Report modules might accidentally depend on raw result fields through shared helpers -> Keep report page props and hooks narrow, and test a completed job route with large overlay artifacts present.
- Splitting hooks can duplicate some job/report fetch logic -> Centralize low-level client functions and keep page-specific hooks as thin orchestration layers.
- Overlay status may briefly show loading or unavailable before the artifact completes -> Make copy precise and avoid implying the analysis failed while only the visual layer is pending.
- Visual workspace may render before overlays, causing a visible layer pop-in -> This is acceptable for usability; status rail should make the loading state clear.
- Future report types may need raw result data -> Add those as explicit opt-in fetches for that report type rather than restoring a global heavyweight load.

## Migration Plan

1. Add or refactor frontend hooks so report routes can load only job summary and report payload.
2. Update `ReportPage` to use the lightweight report state and keep existing job-aware unavailable, failed, canceled, and not-found states.
3. Update `VisionPage` to load result and overlays separately from the report shell, preserving the source video and status rail while overlay artifacts load.
4. Add layer-specific loading/degraded states to the visual analysis card or status rail.
5. Verify with a completed job that has a very large `pose_overlay.json`: report route renders quickly, visual route remains usable, and pose overlay appears or degrades independently.

Rollback is straightforward because backend contracts remain unchanged: the previous combined hook can be restored if a narrow report-loading path causes unexpected missing data.

## Open Questions

- Should future report types be allowed to opt into raw result loading, or should all report pages rely only on generated report JSON?
- Should large overlay optimization become a follow-up change covering compressed, chunked, or time-windowed artifact retrieval?
