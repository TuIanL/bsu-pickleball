## Environment Preflight

Commands run:

```bash
python3 backend/scripts/validate_rtmpose.py --check-only
backend/.venv/bin/python backend/scripts/validate_rtmpose.py --check-only
backend/.venv/bin/python backend/scripts/validate_rtmpose.py
```

Observed status:

- System `python3` is 3.9.6, below the backend's Python 3.10+ requirement.
- Existing backend `.venv` is Python 3.11.14.
- Existing backend `.venv` has `torch`, `numpy`, and `cv2`.
- Installed `mmpose==1.3.2`, `mmcv==2.1.0`, `mmengine==0.10.7`,
  and `mmdet==3.3.0` into the backend `.venv`.
- Downgraded NumPy to `1.26.4` and OpenCV to `4.10.0.84` to avoid
  `xtcocotools` ABI issues with NumPy 2.x.
- Downloaded the RTMPose Body8-Halpe26 config/checkpoint under
  `models/rtmpose/`.
- Full validation currently requires `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1`
  with PyTorch 2.6+ because the trusted OpenMMLab checkpoint uses the older
  pickle-based format.

Successful single-frame true-model validation:

```bash
MPLCONFIGDIR=/private/tmp/pre-pickleball-mpl \
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 \
backend/.venv/bin/python backend/scripts/validate_rtmpose.py \
  --config models/rtmpose/configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py \
  --checkpoint models/rtmpose/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth \
  --device cpu \
  --bbox 40,24,152,232
```

Result: model initialization and `inference_topdown` completed on CPU and
emitted a `PoseOverlayFrame` with one subject and 26 Halpe26 keypoints. The
synthetic validation frame is not a real person, so low confidence/visibility is
expected.

## Short-Video Pipeline Verification

Verified completed real job `job-201203dacb` after installing the optional
MMPose/MMCV/MMEngine runtime and RTMPose Body8-Halpe26 assets.

Commands run:

```bash
curl -s http://localhost:8000/api/analysis/jobs/job-201203dacb/result
curl -s http://localhost:8000/api/analysis/jobs/job-201203dacb/artifacts/pose-overlay
python3 - <<'PY'
import json
from pathlib import Path
p=Path('backend/data/outputs/job-201203dacb/pose_overlay.json')
data=json.loads(p.read_text())
frames=data.get('frames',[])
subjects=sum(len(f.get('subjects',[])) for f in frames)
names={kp.get('name') for f in frames for s in f.get('subjects',[]) for kp in s.get('keypoints',[])}
print(data.get('status'), data.get('keypoint_schema'), len(frames), subjects, len(names), 'hip' in names)
PY
```

Observed status:

- Pipeline result status is `completed`.
- Pose stage is `done` with detail `已生成 4608 组骨架关节`.
- Pose artifact endpoint returns `status=available`, `keypoint_schema=rtmpose26`,
  and 27 skeleton edges.
- Persisted `pose_overlay.json` contains 775 frames, 4608 subjects, 26 keypoints
  per subject, 26 unique Halpe26 keypoint names including `hip`, confidence
  values, visible flags, frame indices, timestamps, track IDs, and bboxes.
- Frontend workspace `/analysis/job-201203dacb/vision` renders source video,
  YOLO boxes, and RTMPose joints/edges; the existing `人框` and `骨架` controls
  toggle those layers independently.

## Regression Checks

Commands run:

```bash
cd backend
../backend/.venv/bin/python -m pytest tests/test_rtmpose26_adapter.py tests/test_api_smoke.py -q
../backend/.venv/bin/python -m pytest -q
cd ..
npm run build
```

Observed status:

- Focused RTMPose adapter/API tests: 22 passed.
- Full backend tests: 43 passed.
- Frontend production build completed successfully.
