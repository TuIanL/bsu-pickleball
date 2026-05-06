## Context

The current React + TypeScript app is a single scrolling product demo. `App.tsx` renders the header, report workspace, diagnosis, training loop, platform flow, hardware preview, and footer in one vertical document. The existing mock data already contains useful domain concepts such as metrics, court points, routes, movement paths, rallies, diagnoses, training recommendations, and hardware preview values, but the interface does not yet express a layered product flow.

The desired direction is a premium AI sports video analysis product for pickleball: a dark, video-first experience with clean SaaS cards, neon green action states, simulated court/video overlays, coach-like insights, and clear drill-down paths. The implementation must avoid PB Vision or SwingVision logos, brand names, original imagery, original icons, and original copy while preserving the general quality bar of a mature sports analytics product.

## Goals / Non-Goals

**Goals:**

- Convert the current long page into a layered app with overview, visual analysis, report detail, training, and hardware pages.
- Make `/vision` the primary product experience: a simulated video analysis workspace with court lines, player markers, shot trajectories, labels, highlights, AI coach notes, score context, and rally timeline.
- Provide report entry buttons from `/vision` into `/reports/landing`, `/reports/movement`, `/reports/rally`, and `/reports/diagnosis`.
- Reuse and extend existing mock data so metrics, court visualizations, diagnosis, training recommendations, and hardware values still feel connected.
- Refresh the visual style toward dark premium sports tech with restrained bright green accents, responsive layouts, hover states, and presentation-ready screenshots.
- Keep the app fully local and demo-friendly without backend services or real video, computer vision, or hardware integrations.

**Non-Goals:**

- Implement real video upload, playback processing, computer vision, pose estimation, ball tracking, or sensor fusion.
- Add authentication, persistence, payments, account management, team management, or backend APIs.
- Copy third-party product branding, logos, images, icons, or wording.
- Build a generic admin dashboard dominated by tables.
- Replace all future API shapes with final production schemas; this change only needs structured mock data that is easy to replace later.

## Decisions

### Use lightweight internal routing instead of adding a router dependency

The app can represent routes such as `/`, `/vision`, `/reports/:type`, `/training`, and `/hardware` with local navigation state plus History API handling. This keeps the demo dependency-light and avoids introducing a routing package for a small static prototype.

Alternatives considered:

- React Router: stronger for a production multi-page app, but unnecessary for the current static demo unless route complexity grows.
- Separate HTML pages: simple but would duplicate layout, data imports, and styling.

### Treat `/vision` as the product anchor

The overview page should explain the platform quickly, but `/vision` should carry the strongest screenshot value and interaction density. It should combine SwingVision-like dark sports-tech energy with PB Vision-like clean SaaS structure: central video mock, right-side highlights and coach notes, bottom timeline, and report CTAs.

Alternatives considered:

- Keep the current report as the first screen: preserves existing behavior but does not solve the "everything is listed on one page" problem.
- Make `/reports` the primary page: useful for data, but less compelling than video-first analysis for demos and roadshow screenshots.

### Use Tailwind CSS for the redesign while preserving TypeScript component boundaries

Tailwind CSS is a good fit for high-fidelity interface work with many cards, chips, hover states, responsive grids, and dark theme tokens. The implementation can add Tailwind configuration and move new UI styling into class names while keeping existing TypeScript components or extracting shared primitives where useful.

Alternatives considered:

- Continue only with the existing CSS file: avoids setup but makes a large visual redesign slower and harder to keep consistent.
- Add a full component library: could speed up basic controls, but risks making the product look generic and adds more dependency surface.

### Model analysis content as page-ready mock data

Mock data should expand from report-only objects into page-ready entities: navigation items, match summary, video overlay events, highlights, coach notes, report cards, report detail definitions, shot explorer rows, skill ratings, drills, and progress trends. These objects should stay local and typed.

Alternatives considered:

- Hard-code content inside JSX: faster for the first screen, but brittle when report pages and training links need to share data.
- Over-design production API schemas now: premature without real algorithm outputs.

### Simulate video analysis with CSS and SVG layers

The central video player should use custom CSS/SVG to draw an abstract pickleball court, kitchen zones, player dots or boxes, shot paths, heat points, labels, score, current rally, controls, and timeline markers. It does not need an actual video asset.

Alternatives considered:

- Use a stock or scraped sports image: risks copyright/brand mismatch and may not show pickleball-specific analysis clearly.
- Use canvas/WebGL: useful for real animation, but too heavy for this static high-fidelity demo.

### Preserve existing capabilities as dedicated pages

Training and hardware content should not disappear; they should become pages linked from the navigation and from relevant insights. Existing report, training, and hardware components can be adapted, but the page layout should feel purpose-built rather than simply moving old sections behind tabs.

Alternatives considered:

- Hide existing sections under collapsible panels: still feels like one-page content organization.
- Delete hardware preview until later: would weaken the project's TENG-IMU roadmap narrative.

## Risks / Trade-offs

- [Risk] The redesign could become visually impressive but less clear for judges or coaches. -> Mitigation: keep page labels, CTA text, report types, and coach notes concrete and action-oriented.
- [Risk] Adding Tailwind could create a mixed styling system during transition. -> Mitigation: scope the change to the redesigned app shell and migrate or retire old CSS deliberately.
- [Risk] Simulated video overlays could look fake if too decorative. -> Mitigation: use pickleball-specific court geometry, rally metadata, shot labels, score, and timeline markers tied to mock data.
- [Risk] Multi-page navigation can feel broken in a static Vite demo if deep links are not handled. -> Mitigation: support route state and History API navigation for all declared routes, with a fallback to overview.
- [Risk] Too many dashboard modules may dilute the visual analysis center. -> Mitigation: keep video workspace first and largest, with metrics, shot explorer, skill ratings, drills, and trends organized below.

## Migration Plan

1. Add Tailwind configuration and baseline global theme tokens while keeping the app locally runnable with Vite.
2. Introduce typed mock data for navigation, match summary, video overlays, highlights, coach notes, report types, shot explorer rows, skill ratings, drills, progress trends, and hardware content.
3. Replace the single-scroll `App.tsx` composition with a layered app shell and route-level page rendering.
4. Build the overview and `/vision` pages first because they define the visual system and primary product flow.
5. Build `/reports/:type`, `/training`, and `/hardware` pages using shared page shell, cards, buttons, chips, and visualization components.
6. Validate desktop and mobile responsive layouts and ensure no text overlap, broken navigation, or blank visualization states.

Rollback is straightforward because the change is front-end only: restore the previous single-page composition and remove the new route/page/mock-data additions.

## Open Questions

- Should the visible product name remain `拍动视析` for Chinese project continuity, switch to an English demo name such as `PickleMotion AI`, or show both?
- Should route paths be visible in the URL for presentation, or is in-app navigation state enough for the first implementation?
- Should the first implementation include Chinese-first copy, English-first copy, or a mixed bilingual tone for roadshow visuals?
