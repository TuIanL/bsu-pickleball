# Local Runtime and Research Storage

This directory is for local files produced or consumed by the analysis backend. The project now treats these files as product runtime state and research evidence, not disposable presentation assets.

- `uploads/`: uploaded source videos
- `outputs/jobs/`: durable job records with lifecycle state, input/config signatures, stage telemetry, error codes, cancellation timing, and worker metadata
- `outputs/`: generated pipeline JSON, report JSON, tracking overlays, pose overlays, optional ball analysis artifacts, and legacy overlays
- `reports/`: legacy or generated analysis JSON
- `tmp/`: extracted frames and temporary processing files

Keep large videos, generated reports, frame dumps, and training datasets out of git.

Research-facing records should preserve enough context to reproduce or compare an
analysis run: uploaded video reference, calibration reference, frame stride, model
runtime configuration, per-stage timing, public error code, and generated artifacts.
Internal diagnostic fields are for engineering review and should not be surfaced
directly in user-facing UI.

Ball analysis artifacts are configuration-gated runtime outputs. When
`PICKLEBALL_ENABLE_BALL_DETECTION=true` and a valid detector is available, jobs
may write:

- `outputs/<job_id>/detections.jsonl`
- `outputs/<job_id>/ball_trajectory.json`
- `outputs/<job_id>/cleaned_ball_trajectory.json`
- `outputs/<job_id>/bounce_events.json` when bounce detection is enabled
- `outputs/<job_id>/ball_overlay.json` when a later overlay writer produces it

Missing ball artifacts are not automatically errors: they can mean the feature
was disabled, the model dependency was unavailable, or no usable ball candidate
was detected. Hit events, shot classification, scoring, tactical conclusions,
and complete rally segmentation still require dedicated downstream capabilities.
