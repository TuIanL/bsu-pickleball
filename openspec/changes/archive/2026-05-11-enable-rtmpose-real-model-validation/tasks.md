## 1. Runtime And Model Setup

- [x] 1.1 Document the required Python 3.10+ RTMPose validation environment, including PyTorch, MMPose, MMCV/MMEngine, NumPy, OpenCV, and CPU/GPU device expectations.
- [x] 1.2 Add optional backend dependency metadata for RTMPose validation without making the lightweight backend install require MMPose or model files.
- [x] 1.3 Update `models/README.md` with the supported Body8-Halpe26 config/checkpoint names, download locations, ignored local paths, and environment variable examples.
- [x] 1.4 Verify the local environment reports clear installed/missing status for `torch`, `mmpose`, `mmcv`, `mmengine`, `numpy`, and `cv2`.

## 2. Schema And Adapter Alignment

- [x] 2.1 Align `RTMPOSE26_KEYPOINT_NAMES` with MMPose Halpe26 metadata, including the index-19 `hip` keypoint.
- [x] 2.2 Align default skeleton edges with the supported Halpe26 skeleton metadata while preserving frontend render compatibility.
- [x] 2.3 Harden `RTMPose26Adapter` validation for unsupported schema names, incompatible keypoint counts, empty bbox lists, and MMPose output shape variations.
- [x] 2.4 Add focused tests for keypoint normalization, visible/confidence handling, schema mismatch diagnostics, and empty-subject behavior without importing MMPose.

## 3. Single-Frame True-Model Validation

- [x] 3.1 Add a local validation command or script that checks dependency imports, model asset paths, device selection, `init_model`, and `inference_topdown`.
- [x] 3.2 Make the validation path accept or create a frame plus one or more `xyxy` person boxes and print/save normalized `PoseOverlayFrame` JSON.
- [x] 3.3 Ensure validation failures identify the failing prerequisite or inference step instead of returning a generic stack trace.
- [x] 3.4 Run the single-frame validation with configured RTMPose assets and record the command/result in the change notes or task evidence.

## 4. Pipeline And Artifact Verification

- [x] 4.1 Run a calibrated short-video analysis with YOLO/tracking and RTMPose enabled using the supported model assets.
- [x] 4.2 Confirm the completed result reports a done pose stage, `pose_overlay_status=available`, and a retrievable `pose_overlay_url`.
- [x] 4.3 Inspect the persisted `pose_overlay.json` for frame indices, timestamps, subject track IDs, bboxes, Halpe26 keypoint names, confidence values, visible flags, and skeleton edges.
- [x] 4.4 Verify missing dependency, missing asset, no-player-box, and pose inference failure paths produce clear unavailable/skipped states without failing detection-only analysis.

## 5. Frontend Verification

- [x] 5.1 Open the completed real-job visual workspace and verify source video playback renders synchronized RTMPose joints and skeleton edges.
- [x] 5.2 Verify skeleton overlay toggling hides/shows joints without breaking video playback or YOLO box overlays.
- [x] 5.3 Verify completed detection-only or pose-unavailable jobs keep person boxes visible and communicate the skeleton unavailable reason.

## 6. Regression Checks

- [x] 6.1 Run backend unit/API tests that do not require RTMPose assets and confirm lightweight imports still pass.
- [x] 6.2 Run frontend type/build checks for the visual workspace and overlay data types.
- [x] 6.3 Reconcile task 7.4 in `add-yolo-rtmpose-video-overlays` after true-model skeleton rendering is verified.
