# Python Vision Backend Foundation

This backend is the lightweight API boundary for the pickleball visual-analysis workflow. It intentionally starts with mock analysis results so the product flow can be built before YOLO11, RTMPose26, CUDA, model weights, or uploaded videos are required.

## Run Locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

The frontend can call this service with:

```bash
VITE_ANALYSIS_API_URL=http://localhost:8000 npm run dev
```

If the backend is not running, the frontend falls back to a local mock job in browser storage.

## API Surface

- `GET /health`
- `POST /api/analysis/jobs`
- `GET /api/analysis/jobs/{job_id}`
- `GET /api/analysis/jobs/{job_id}/report`

The current job service completes mock jobs immediately. Real processing can later replace `app/services/mock_analysis.py` with a worker-backed pipeline.

## Storage Conventions

- `storage/uploads/`: uploaded source videos
- `storage/reports/`: generated analysis report JSON
- `storage/tmp/`: extracted frames and temporary processing files
- `models/`: local model weights and checkpoints

These folders are local runtime/storage locations. Large files, generated outputs, model checkpoints, videos, frames, and training datasets must not be committed.

## Future Vision Adapters

Reserved adapter boundaries live under `app/vision/`:

- `detectors/`: future YOLO11 object detector adapters
- `pose/`: future RTMPose26 pose-estimation adapters
- `tracking/`: player, ball, and paddle tracking
- `court/`: court calibration and pixel-to-court mapping
- `events/`: shot, landing, rally, and diagnosis event extraction

YOLO11 output should be normalized to stable labels such as `player`, `ball`, `paddle`, and court-specific labels before report generation. RTMPose26 output should be normalized into named keypoints or pose-derived features before diagnosis logic consumes it.
