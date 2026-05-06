## 1. Project Setup

- [x] 1.1 Initialize a Vite + React + TypeScript front-end application in the repository.
- [x] 1.2 Add required UI dependencies, including an icon library suitable for interface controls.
- [x] 1.3 Configure basic scripts for development, build, linting, and preview.
- [x] 1.4 Establish a simple source structure for components, data, types, and styles.

## 2. Demo Data Model

- [x] 2.1 Define TypeScript domain types for report sessions, metrics, rallies, court events, diagnoses, training recommendations, and hardware sensor preview data.
- [x] 2.2 Create structured local demo data for one complete pickleball training or match report.
- [x] 2.3 Keep visual report data and TENG-IMU hardware preview data in separate objects so they can be replaced independently later.
- [x] 2.4 Centralize product copy for report labels, diagnosis text, and phase-two hardware disclaimers.

## 3. App Shell And Visual System

- [x] 3.1 Build a Chinese-first single-page app shell for "拍动视析".
- [x] 3.2 Create a restrained sports-technology visual system with responsive layout rules and stable panel dimensions.
- [x] 3.3 Make the first viewport open directly into the post-session report workspace with summary context and primary visualization.
- [x] 3.4 Add compact navigation or section controls for report, diagnosis, training loop, and hardware preview areas.

## 4. Interactive Performance Report

- [x] 4.1 Implement summary metric cards for overall score, ball speed, movement efficiency, rally stability, and landing accuracy.
- [x] 4.2 Implement a pickleball court visualization with landing heat points, shot routes, and player movement path.
- [x] 4.3 Add visualization mode controls that switch emphasis between landing distribution, routes, and movement.
- [x] 4.4 Implement rally analysis panels with duration, shot count, route pattern, result, and tactical observation.
- [x] 4.5 Verify the report layout on desktop and mobile viewports with no incoherent overlap or horizontal scrolling.

## 5. Training Feedback Loop

- [x] 5.1 Implement personalized diagnosis cards with severity, evidence, and issue names.
- [x] 5.2 Connect each diagnosis to a concrete improvement suggestion, priority, and expected outcome.
- [x] 5.3 Build the learning-practice-evaluation loop section linking report issue, teaching placeholder, practice task, and next-session target.
- [x] 5.4 Add progress or goal indicators that show previous-current-next improvement context.
- [x] 5.5 Ensure teaching video and motion comparison modules are presented as placeholders, not as connected real assets.

## 6. Hardware Fusion Preview

- [x] 6.1 Implement a clearly labeled "二期智能球拍接入预览" section.
- [x] 6.2 Display simulated TENG and IMU metrics including sweet-zone hit rate, impact intensity, swing speed, swing path, and hit-quality score.
- [x] 6.3 Implement a 3 by 3 sweet-zone contact visualization with highlighted hit location or distribution.
- [x] 6.4 Explain the fusion relationship between macro visual indicators and micro paddle indicators in the UI.
- [x] 6.5 Keep all simulated hardware values visibly distinguished from live hardware data.

## 7. Verification And Polish

- [x] 7.1 Run lint and production build checks successfully.
- [x] 7.2 Start the local dev server and inspect the site in a browser.
- [x] 7.3 Verify desktop and mobile screenshots for text fit, visualization framing, and responsive behavior.
- [x] 7.4 Fix any visual overlap, cramped controls, missing states, or unreadable text discovered during review.
- [x] 7.5 Summarize implemented files, commands run, and remaining future integration notes.
