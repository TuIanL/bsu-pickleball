## Context

The active `add-yolo-rtmpose-video-overlays` change already added pose schemas, a lazy `RTMPose26Adapter`, pipeline calls to `estimate_frame(...)`, pose artifact persistence, and frontend skeleton rendering. Its remaining task 7.4 is blocked because the local machine has no Python 3.10+ backend environment, no PyTorch/MMPose/MMCV/MMEngine/OpenCV runtime, and no RTMPose config/checkpoint files in `models/`.

The existing code intentionally keeps heavy model imports lazy so the API can still start without RTMPose. This change should keep that property while making the true-model path explicit, reproducible, and verifiable.

## Goals / Non-Goals

**Goals:**

- Document and verify the optional RTMPose runtime without making lightweight backend imports depend on MMPose or CUDA.
- Use a concrete first supported model pair: OpenMMLab RTMPose Body8-Halpe26 26-keypoint config and checkpoint.
- Align the backend `rtmpose26` schema with MMPose Halpe26 keypoint names and skeleton connections.
- Add a repeatable single-frame validation path that proves `init_model`, `inference_topdown`, and `RTMPose26Adapter.estimate_frame(...)` can produce `PoseOverlayFrame` data from a frame and person bbox.
- Verify a calibrated short-video job can persist a real `pose_overlay.json`, expose it through the artifact API, and render skeleton joints in the visual workspace.
- Preserve clear skipped/unavailable states for missing dependencies, missing assets, empty detections, CPU/GPU mismatch, and runtime inference errors.

**Non-Goals:**

- Training, fine-tuning, exporting, or benchmarking RTMPose models.
- Adding model weights to git or requiring every developer/test environment to download RTMPose assets.
- Replacing YOLO/tracker with bottom-up pose detection.
- Real-time inference guarantees, GPU scheduling, worker queues, or cloud model storage.
- Pose-based coaching diagnosis beyond displaying skeleton evidence.

## Decisions

### Keep RTMPose dependencies optional

RTMPose remains an optional local runtime path. Base backend tests and imports must continue to work without `torch`, `mmpose`, `mmcv`, `mmengine`, or model files. Documentation should show a dedicated install path for pose validation rather than silently adding fragile heavyweight packages to every environment.

Alternative considered: add MMPose packages to the default backend dependency list. That would make the setup look simpler but risks breaking lightweight CI, non-GPU machines, and developers who only need API/report work.

### Standardize on Body8-Halpe26 RTMPose-m first

The first supported asset pair should be OpenMMLab's RTMPose Body8-Halpe26 26-keypoint `256x192` model because it matches the existing `rtmpose26` contract and is small enough for local validation compared with larger variants.

Alternative considered: use a COCO 17-keypoint RTMPose checkpoint. That is easier to find in examples but would require a separate schema or lossy mapping and would not verify the promised RTMPose26 overlay.

### Store local assets under `models/rtmpose/`

The config and checkpoint should live in ignored local paths such as `models/rtmpose/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py` and `models/rtmpose/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth`. Environment variables should point to these files when running the backend.

Alternative considered: download model files at backend startup. That hides important setup work, adds network flakiness to analysis jobs, and makes failures harder to diagnose.

### Validate adapter output before full pipeline runs

A small local validation command or script should check Python version, dependency importability, asset existence, `init_model`, `inference_topdown`, and normalized `PoseOverlayFrame` output against a synthetic or saved single frame plus bbox. Full-video verification should run only after this passes.

Alternative considered: use only end-to-end video runs. That gives a realistic result but makes failures harder to isolate because video upload, calibration, YOLO, tracking, pose, artifact storage, and frontend rendering are all in play at once.

### Align schema to MMPose Halpe26 metadata

The backend keypoint names and skeleton edges should use the same 26-point semantics as MMPose's `halpe26.py`, including the `hip` keypoint at index 19. The schema name can remain `rtmpose26`, but unsupported keypoint counts or schema names must produce clear failure details.

Alternative considered: keep the existing `pelvis` name. That is close semantically, but it diverges from the model metadata and can break edge rendering or future model comparisons.

## Risks / Trade-offs

- [Risk] MMPose/MMCV installation can vary by Python, PyTorch, CUDA, and macOS/Linux platform. Mitigation: document Python 3.10+ setup, CPU/GPU device variables, MIM/MMCV guidance, and a preflight validation command.
- [Risk] CPU RTMPose inference may be slow on local videos. Mitigation: keep overlay frame stride configurable and validate with a short clip first.
- [Risk] YOLO may produce no usable player boxes, preventing pose inference even when RTMPose works. Mitigation: separate single-frame adapter validation from full pipeline validation and keep no-box pose stages explicit.
- [Risk] Model asset URLs or package APIs may change upstream. Mitigation: pin the documented config/checkpoint names and keep adapter calls tolerant of known `inference_topdown` signatures.
- [Risk] Frontend may appear empty if low-confidence joints are all hidden. Mitigation: preserve confidence/visible fields and verify with a clip where player boxes cover the body clearly.

## Migration Plan

1. Keep existing detection-only and pose-unavailable behavior as the default until `PICKLEBALL_ENABLE_POSE_INFERENCE=true` and asset paths are configured.
2. Add optional RTMPose setup documentation and validation commands without committing model weights.
3. Align keypoint schema metadata and adapter validation around Halpe26.
4. Run single-frame RTMPose validation, then a calibrated short-video job, then frontend visual inspection.
5. If validation fails in a developer environment, disable pose inference and retain the existing YOLO/tracking overlay flow.

## Open Questions

- Should the implementation add a dedicated `RTMPOSE_*` env alias in addition to the existing `PICKLEBALL_RTMPOSE_*` names, or keep only the current project-prefixed variables?
- Should the validation script create a synthetic bbox/frame, reuse a checked-in tiny fixture, or accept a user-provided image path?
- Should the first true-model verification use CPU by default on macOS, with `cuda:0` documented for compatible Linux/NVIDIA setups?
