## Why

RTMPose skeleton overlays are wired through the backend and frontend contracts, but task 7.4 cannot be completed because the local runtime lacks Python 3.10+, PyTorch/MMPose/MMCV/MMEngine/OpenCV, and real RTMPose model assets. The project needs a repeatable true-model validation path so `pose_overlay_status=available` means real RTMPose inference, not only injected test doubles or degraded states.

## What Changes

- Add a documented optional RTMPose runtime setup for Python 3.10+, PyTorch, MMPose, MMCV/MMEngine, NumPy, and OpenCV, including CPU/GPU device selection.
- Standardize the first supported model asset pair on OpenMMLab RTMPose Body8-Halpe26 26-keypoint config and checkpoint stored under ignored `models/` paths.
- Align the backend `rtmpose26` keypoint names and skeleton edges with the MMPose Halpe26 metadata used by the chosen checkpoint.
- Add a local validation path that verifies `mmpose.apis.init_model`, `inference_topdown`, single-frame bbox inference, and normalized `PoseOverlayFrame` output.
- Define end-to-end verification for calibrated short-video jobs so pose artifacts are persisted and the visual workspace renders real skeleton joints.
- Preserve optional/degraded behavior when pose dependencies, model files, player boxes, CUDA, or inference calls are unavailable.

## Capabilities

### New Capabilities

- `rtmpose-real-model-validation`: Local RTMPose dependency setup, model asset contract, adapter validation, single-frame inference, and short-video pose overlay verification.

### Modified Capabilities

- `video-analysis-job-flow`: Completed real analysis jobs with configured RTMPose assets must expose true-model pose stage details and retrievable pose overlay artifacts when skeleton inference succeeds.
- `visual-analysis-workspace`: Completed real jobs with available pose artifacts must render skeleton joints from true RTMPose output while preserving unavailable/degraded states.

## Impact

- Backend optional dependencies and documentation in `backend/requirements.txt`, `backend/pyproject.toml`, `backend/README.md`, and `models/README.md`.
- Pose schemas and adapter behavior in `backend/app/schemas/pose.py` and `backend/app/vision/pose/rtmpose26_adapter.py`.
- Pipeline pose stage reporting and artifact behavior in `backend/app/services/analysis_pipeline.py`.
- Focused validation scripts or tests under backend tooling/tests for dependency checks and single-frame RTMPose adapter output.
- Local model files under `models/`, remaining ignored by git.
- Manual verification of the frontend visual workspace skeleton layer after a true-model backend run.
