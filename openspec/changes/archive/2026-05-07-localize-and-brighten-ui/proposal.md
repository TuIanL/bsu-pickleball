## Why

The current product demo still mixes English and Chinese across navigation, report labels, video overlays, metrics, chart legends, tables, and calls to action, which weakens its fit for a Chinese competition/presentation context. The overall black sports-tech palette also feels heavy for a public-facing innovation showcase, while the existing green, lime, blue, orange, and red accent system is worth preserving.

## What Changes

- Replace visible English product copy with natural Chinese copy across the overview, navigation shell, visual analysis workspace, report detail pages, training page, hardware preview, cards, tables, chips, tooltips, and CTAs.
- Convert the app's primary visual theme from dark black surfaces to a brighter, lightweight sports-analysis interface.
- Preserve the current secondary accent relationships: neon green for positive/action states, lime for secondary performance cues, blue for analysis/training, orange for risk, and red for errors.
- Keep the existing React/Vite/Tailwind architecture, local mock data model, page routing, and interactive demo behavior intact.
- Ensure the updated bright UI remains readable, presentation-ready, and stable on desktop and mobile viewports.

## Capabilities

### New Capabilities
- `localized-bright-ui`: Covers global Chinese localization and the brighter product presentation layer across all existing demo pages.

### Modified Capabilities
- `visual-analysis-workspace`: Replace the explicit dark sports-tech visual style requirement with a bright sports-tech style that preserves video-analysis hierarchy and accent semantics.

## Impact

- Affected code: `src/index.css`, `src/App.tsx`, `src/data/demoData.ts`, and platform components under `src/components/platform/`.
- No API, backend, routing, or dependency changes are expected.
- Verification should include text search for remaining visible English strings and visual checks of the bright theme on desktop and mobile.
