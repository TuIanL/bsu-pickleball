# Local Runtime Storage

This directory is for local files produced or consumed by the analysis backend.

- `uploads/`: uploaded source videos
- `outputs/`: generated pipeline JSON, report JSON, tracking overlays, pose overlays, and ball overlays
- `reports/`: legacy or generated analysis JSON
- `tmp/`: extracted frames and temporary processing files

Keep large videos, generated reports, frame dumps, and training datasets out of git.

Ball overlay artifacts are stored per job as
`outputs/<job_id>/ball_overlay.json`. They may contain observed detector points
and repaired short-gap trajectory points; both should stay out of git with the
rest of generated runtime output.
