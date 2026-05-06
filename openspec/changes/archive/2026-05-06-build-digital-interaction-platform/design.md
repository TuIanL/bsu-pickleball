## Context

The repository is effectively a new project with only OpenSpec configuration in place. The product direction comes from the project plan: "拍动视析" is a pickleball sports performance analysis platform based on visual capture now and future TENG-IMU smart paddle data.

The first software milestone is a front-end demonstration website for innovation project review, product explanation, and early venue or training institution conversations. It must feel like a working analysis platform, not a static brochure.

Primary stakeholders:

- Project team presenting the innovation training project.
- Reviewers who need to understand technical feasibility and product value quickly.
- Pickleball venues, coaches, training institutions, and players who need a concrete service scenario.

## Goals / Non-Goals

**Goals:**

- Build a polished single-page web app that opens directly into an interactive performance report demo.
- Show the end-to-end software story: visual analysis report, personalized diagnosis, learning-practice-evaluation loop, and future smart paddle fusion.
- Use structured local mock data so the first version works without backend services, computer vision pipelines, or physical hardware.
- Keep the architecture ready for future replacement of mock data with real report APIs and TENG-IMU sensor feeds.
- Provide responsive desktop and mobile layouts suitable for live demonstrations.

**Non-Goals:**

- Implement real computer vision, pose estimation, ball tracking, or sensor fusion algorithms.
- Implement authentication, persistent user accounts, payment, subscriptions, or admin management.
- Implement QR-code report publishing or real venue deployment infrastructure.
- Implement a real 3D skeletal comparison engine; first version may use visual placeholders or simplified motion comparison panels.
- Connect to real TENG, IMU, camera, or MCU hardware.

## Decisions

### Use a Vite + React + TypeScript front-end

The project should initialize as a Vite React TypeScript app because it is fast to scaffold, simple to deploy, and well suited for a component-driven product demo.

Alternatives considered:

- Static HTML/CSS/JS: lower setup cost, but weaker structure for reusable report, diagnosis, and sensor-preview components.
- Next.js: strong full-stack option, but unnecessary for a local demo with no server-rendering or backend needs.

### Make the first screen a report workspace

The home experience should open directly into a "赛后分析报告" workspace with summary metrics, court visualization, and report controls visible in the first viewport. Project background and technical explanation can appear as supporting sections after the demo.

Alternatives considered:

- Marketing landing page first: easier to explain the project, but weaker for judges and partners who need proof of the product concept.
- Multi-page app: closer to a production system, but slower for a first demonstration and less effective in a short pitch.

### Model the demo data as future API-shaped domain objects

Mock data should be stored as typed domain objects for sessions, metrics, rallies, court events, diagnoses, training recommendations, and sensor-preview values. Components should consume these objects rather than hard-coded text blocks.

This keeps the first implementation honest: future API responses can replace the local data source without rewriting the interface.

### Use custom lightweight visualizations for the first version

The first version can render the court, heat points, movement path, shot routes, sweet-zone grid, and swing preview with SVG/CSS/HTML components. A charting library is not required unless implementation discovers that built-in rendering becomes too brittle.

Alternatives considered:

- Full chart library from the start: useful for dashboards, but may add visual weight and dependency complexity.
- Canvas/WebGL: powerful for motion playback, but unnecessary until real trajectories or animation timelines exist.

### Label future hardware capabilities clearly

The TENG-IMU section should be framed as "二期智能球拍接入预览" and use simulated values. It should still feel concrete by showing metrics such as sweet-zone hit rate, impact intensity, swing speed, swing path, and a composite hit-quality score.

This prevents the demo from overstating current hardware readiness while preserving the roadmap narrative from the project plan.

## Risks / Trade-offs

- [Risk] The site could feel like a dashboard with fake numbers rather than a credible product demo -> Mitigation: pair every metric with a visible scenario, such as court events, movement path, diagnosis, and recommended next training task.
- [Risk] First-version mock data may diverge from future algorithm output -> Mitigation: define typed data structures around stable domain concepts: session, rally, shot, position, diagnosis, recommendation, and sensor reading.
- [Risk] Hardware-preview claims may look overpromised -> Mitigation: explicitly label the module as phase-two preview and distinguish visual data from TENG-IMU data.
- [Risk] Too many sections may make the page feel like a brochure -> Mitigation: keep the report workspace as the primary interaction surface and make supporting sections compact.
- [Risk] Responsive layouts may break dense analysis panels on mobile -> Mitigation: design mobile as stacked report cards with stable visualization aspect ratios rather than shrinking desktop panels blindly.

## Migration Plan

1. Initialize the front-end application and build the first static demo using local data.
2. Replace individual mock data modules with API responses as visual analysis services become available.
3. Add report identity and QR entry points once report generation and hosting exist.
4. Add smart paddle ingestion views after TENG-IMU sample data formats are finalized.

Rollback is simple for this phase: the change is additive and can be removed by deleting the new front-end app files and OpenSpec change.

## Open Questions

- Will the first implementation use English, Chinese, or bilingual labels? Current recommendation: Chinese-first for the project review context.
- Should the demo focus on a professional athlete scenario, a public venue player scenario, or allow switching between both?
- Does the project team already have preferred brand colors, logo assets, or visual identity for "拍动视析"?
- Should the first version include a simulated QR-code entry, or leave QR reporting for a later change?
