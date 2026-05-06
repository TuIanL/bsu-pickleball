## Why

The current product demo presents report, diagnosis, training, and hardware preview content in one long scrolling page, which makes the platform feel like a polished brochure rather than a mature AI sports video analysis product. This change upgrades the experience into a layered pickleball analysis platform where users start from an overview, enter a video-first visual analysis workspace, and drill into focused report, training, and hardware pages.

## What Changes

- Introduce a page-level information architecture with dedicated routes for overview, visual analysis, report details, training recommendations, and phase-two hardware fusion.
- Add a premium sports-tech visual analysis page centered on a simulated video player with pickleball court lines, player markers, shot trajectories, heat/placement overlays, AI labels, score context, rally metadata, controls, and timeline markers.
- Add a right-side Highlights / AI Coach Notes experience that connects key rally moments to actionable strengths, risks, errors, and training suggestions.
- Add report entry buttons from the visual analysis page for landing analysis, movement analysis, rally tactics, and motion diagnosis.
- Add report detail pages under `/reports/:type` that present core metrics, charts or court visualizations, and interpretation tied to the selected report type.
- Promote training recommendations and hardware fusion preview from long-page sections into dedicated pages while preserving their existing product narrative.
- Refresh the visual system toward a dark premium sports analytics interface with clean SaaS cards, bright green CTAs, refined hover states, responsive layouts, and mock data only.
- Add structured mock data needed for video events, highlights, shot filters, report cards, skill ratings, drills, progress trends, and report route links.

## Capabilities

### New Capabilities

- `layered-product-navigation`: Covers the multi-page information architecture, top navigation, route-level page transitions, and report entry flow.
- `visual-analysis-workspace`: Covers the video-first AI analysis page, simulated player/court overlays, highlights, coach notes, rally timeline, shot filters, and report CTA entry points.
- `report-detail-pages`: Covers `/reports/:type` pages for landing, movement, rally tactics, and motion diagnosis reports with typed content, metrics, visualizations, and explanations.

### Modified Capabilities

- `interactive-performance-report`: Changes the existing report-first single-page requirement so performance report content can be reached through layered navigation and focused report pages while preserving core metrics, court visualization, and rally interpretation.
- `training-feedback-loop`: Changes training feedback from an inline page section into a dedicated training page linked from report and coach-note recommendations.
- `hardware-fusion-preview`: Changes the phase-two smart paddle preview from an inline page section into a dedicated hardware page that still clearly labels simulated TENG-IMU values.

## Impact

- Affects React application composition, navigation state or routing, page components, shared layout, and mock data structures.
- Affects existing report, training, and hardware components because they will be reused or reshaped into route-level pages rather than stacked sections.
- May add Tailwind CSS configuration and replace or supplement the current single CSS file with utility-based styling for the refreshed interface.
- Does not add backend, authentication, real video playback, real computer vision, real sensor feeds, or third-party brand assets.
