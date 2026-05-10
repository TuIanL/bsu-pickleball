## ADDED Requirements

### Requirement: Optional RTMPose runtime setup
The backend SHALL provide a documented optional RTMPose runtime setup that can be installed and validated separately from the lightweight API/runtime path.

#### Scenario: Developer checks runtime prerequisites
- **WHEN** a developer prepares RTMPose validation locally
- **THEN** the project documents the required Python version, PyTorch availability, MMPose/MMCV/MMEngine imports, NumPy import, OpenCV import, and CPU/GPU device selection expectations

#### Scenario: Lightweight backend runs without pose runtime
- **WHEN** pose inference is disabled or RTMPose dependencies are not installed
- **THEN** backend imports and non-pose tests continue to run without importing MMPose, loading model files, or requiring CUDA

### Requirement: RTMPose model asset contract
The backend SHALL define the first supported RTMPose26 model assets as OpenMMLab RTMPose Body8-Halpe26 26-keypoint config and checkpoint files stored in ignored local model paths.

#### Scenario: Model assets are configured
- **WHEN** pose inference is enabled and configured paths point to the supported RTMPose Body8-Halpe26 config and checkpoint
- **THEN** the adapter lazily initializes the model using `mmpose.apis.init_model` on the configured device

#### Scenario: Model assets are absent
- **WHEN** pose inference is enabled but the config or checkpoint path is missing or unreadable
- **THEN** validation and pipeline execution report a clear unavailable or skipped pose state and do not advertise a skeleton artifact as available

### Requirement: Halpe26 keypoint schema alignment
The backend SHALL align its `rtmpose26` keypoint names and skeleton metadata with the MMPose Halpe26 26-keypoint metadata used by the supported RTMPose checkpoint.

#### Scenario: RTMPose returns 26 keypoints
- **WHEN** the adapter receives 26 keypoints from the supported model
- **THEN** it serializes them using stable Halpe26-compatible names, confidence values, pixel coordinates, and visible flags

#### Scenario: Unsupported schema is configured
- **WHEN** the configured keypoint schema or model output is incompatible with the supported `rtmpose26`/Halpe26 contract
- **THEN** the backend reports an explicit unsupported-schema or incompatible-output detail instead of silently producing misleading skeleton data

### Requirement: Single-frame RTMPose validation
The backend SHALL provide a local validation path that proves true RTMPose inference can run on one frame and one or more person bounding boxes before full video analysis is attempted.

#### Scenario: Single-frame validation succeeds
- **WHEN** the runtime dependencies, config path, checkpoint path, device, frame, and person bbox are valid
- **THEN** the validation path runs `inference_topdown` and emits a normalized `PoseOverlayFrame` containing at least one subject with keypoint coordinates and confidence values

#### Scenario: Single-frame validation fails
- **WHEN** dependency imports, model initialization, image/frame loading, bbox conversion, or RTMPose inference fails
- **THEN** the validation path exits with a clear diagnostic that identifies the failing prerequisite or inference step

### Requirement: Full pose overlay verification
The backend SHALL support a repeatable short-video verification path that confirms true RTMPose output is persisted as a pose overlay artifact for a calibrated real analysis job.

#### Scenario: Calibrated short-video pose run succeeds
- **WHEN** a readable uploaded video, valid calibration, YOLO/tracking boxes, RTMPose runtime, and supported model assets are configured
- **THEN** the pipeline completes with the pose stage marked done, persists `pose_overlay.json`, sets pose overlay status to `available`, and exposes a retrievable pose overlay artifact URL

#### Scenario: Calibrated short-video pose run cannot estimate skeletons
- **WHEN** the real analysis job completes but no player boxes or no valid pose keypoints are produced
- **THEN** the pipeline records an explicit no-pose or unavailable pose detail and avoids creating an artifact that looks like successful skeleton inference
