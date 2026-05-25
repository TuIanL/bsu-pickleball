# Local Runtime and Research Storage

This directory is for local files produced or consumed by the analysis backend. The project now treats these files as product runtime state and research evidence, not disposable presentation assets.

- `uploads/`: uploaded source videos
- `outputs/jobs/`: durable job records with lifecycle state, input/config signatures, stage telemetry, error codes, cancellation timing, and worker metadata
- `outputs/`: generated pipeline JSON, report JSON, tracking overlays, pose overlays, and legacy ball overlays
- `reports/`: legacy or generated analysis JSON
- `tmp/`: extracted frames and temporary processing files

Keep large videos, generated reports, frame dumps, and training datasets out of git.

Research-facing records should preserve enough context to reproduce or compare an
analysis run: uploaded video reference, calibration reference, frame stride, model
runtime configuration, per-stage timing, public error code, and generated artifacts.
Internal diagnostic fields are for engineering review and should not be surfaced
directly in user-facing UI.

Ball overlay artifacts may exist from legacy or archived work as
`outputs/<job_id>/ball_overlay.json`, but current real-analysis jobs do not claim
ball tracking, hit events, shot classification, or rally segmentation as supported
outputs.
