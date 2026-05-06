## 1. Project Styling Setup

- [x] 1.1 Add Tailwind CSS dependencies and configuration files for the Vite React TypeScript app.
- [x] 1.2 Replace the current global styling entry with Tailwind base imports and dark sports-tech design tokens.
- [x] 1.3 Verify the app still starts locally after the styling setup.

## 2. Data Model And Mock Content

- [x] 2.1 Extend TypeScript report types for navigation routes, match summary, video overlay events, timeline markers, highlights, coach notes, report actions, shot rows, skill ratings, drills, and progress trends.
- [x] 2.2 Refactor or extend demo data so overview, visual analysis, report pages, training, and hardware pages share structured local mock data.
- [x] 2.3 Add supported report definitions for landing, movement, rally tactics, and motion diagnosis, including metrics, visualization type, insights, and training links.

## 3. App Shell And Navigation

- [x] 3.1 Replace the single-scroll `App.tsx` composition with a layered app shell that renders overview, vision, report detail, training, and hardware pages.
- [x] 3.2 Implement dependency-light route state and History API handling for `/`, `/vision`, `/reports/:type`, `/training`, and `/hardware`.
- [x] 3.3 Build a responsive top navigation with original brand identity, workflow links, demo action, primary analysis or upload CTA, and user/team context.
- [x] 3.4 Add stable fallback behavior for unsupported report routes.

## 4. Overview Page

- [x] 4.1 Build a concise overview page that explains the platform and routes users into the visual analysis workflow.
- [x] 4.2 Add presentation-ready hero content with original copy, dark visual treatment, bright green CTA, and a simulated video preview card.
- [x] 4.3 Add compact overview cards for report analysis, training recommendations, and phase-two hardware fusion.

## 5. Visual Analysis Workspace

- [x] 5.1 Build the `/vision` page layout with central video analysis card, right-side highlights or AI coach notes, bottom rally timeline, and report action buttons.
- [x] 5.2 Create the simulated video player using CSS/SVG court lines, kitchen zones, player markers, shot trajectories, heat or landing indicators, labels, score context, and controls.
- [x] 5.3 Implement local interaction for shot filter chips, selected state, and filtered shot summary or shot list.
- [x] 5.4 Add timeline marker hover or focus labels for key events.
- [x] 5.5 Add hover states and responsive behavior for video card, highlights, coach notes, report CTAs, and shot explorer modules.

## 6. Report Detail Pages

- [x] 6.1 Build a shared report detail page template for `/reports/:type`.
- [x] 6.2 Implement landing analysis content with metrics, court heat or placement visualization, and coaching interpretation.
- [x] 6.3 Implement movement analysis content with metrics, path or balance visualization, and coaching interpretation.
- [x] 6.4 Implement rally tactics content with rally-level metrics, shot pattern summaries, and tactical interpretation.
- [x] 6.5 Implement motion diagnosis content with evidence, severity, suggested correction, and links to training recommendations.

## 7. Training And Hardware Pages

- [x] 7.1 Convert the existing training feedback loop into a dedicated `/training` page with recommended drill cards, goals, evidence, difficulty or duration labels, and progress context.
- [x] 7.2 Convert the existing hardware fusion preview into a dedicated `/hardware` page with clear phase-two labeling, simulated sensor metrics, sweet-zone visualization, and visual-sensor fusion narrative.
- [x] 7.3 Ensure report and coach-note training links navigate to the training page or clearly surface the related recommendation.

## 8. Polish And Verification

- [x] 8.1 Check desktop responsive layout for overview, vision, reports, training, and hardware pages.
- [x] 8.2 Check mobile responsive layout for navigation, video workspace, report cards, charts, training cards, and hardware panels.
- [x] 8.3 Run lint and build commands, then fix any TypeScript, ESLint, or build issues.
- [x] 8.4 Verify the UI does not use PB Vision or SwingVision logos, brand names, original images, original icons, or original copy.
