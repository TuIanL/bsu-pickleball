# rtmpose-real-model-validation Specification

## Purpose
TBD - created by archiving change enable-rtmpose-real-model-validation. Update Purpose after archive.
## Requirements
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

### Requirement: Trusted RTMPose checkpoint loading compatibility

当 RTMPose 配置和 checkpoint 路径已经通过本地资产校验，且路径指向受信任的 OpenMMLab 模型时，适配器 SHALL 在调用 MMPose `init_model` 前建立与当前 PyTorch `weights_only` 默认值兼容的加载上下文。该兼容保障 MUST 由 RTMPose 运行时自身提供，不得只依赖启动脚本或调用方环境变量。

#### Scenario: Direct backend launch loads the supported checkpoint

- **WHEN** 后端通过直接 Uvicorn 命令启动，RTMPose 依赖已安装，且 Body8-Halpe26 config/checkpoint 路径可读
- **THEN** `RTMPose26Adapter` SHALL 成功初始化模型，不得因为 `numpy.ndarray` safe-global 或 `weights_only` 默认值错误而跳过姿态阶段

#### Scenario: Trusted checkpoint loads with the compatibility environment absent

- **WHEN** 进程启动前未设置 `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD`
- **AND** 适配器收到仓库配置的受信任 checkpoint
- **THEN** 适配器 SHALL 在模型初始化前设置或等价地应用兼容策略，并继续执行 `inference_topdown`

#### Scenario: Missing pose runtime remains degraded and explicit

- **WHEN** MMPose 依赖、config 或 checkpoint 不存在
- **THEN** 适配器或 pipeline SHALL 保持现有不可用/跳过行为，并 SHALL NOT 创建看似成功的骨架 artifact

### Requirement: Single-frame validation covers checkpoint compatibility

现有单帧 RTMPose 验证路径 SHALL 在不预设外部 `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD` 的情况下覆盖真实 checkpoint 初始化和推理。

#### Scenario: Validation succeeds without external compatibility setup

- **WHEN** 使用仓库 Body8-Halpe26 config/checkpoint、backend 虚拟环境、一个有效帧和人体框运行验证脚本
- **THEN** 验证 SHALL 返回成功，并输出至少一个包含 26 个关键点的 `PoseOverlayFrame`

#### Scenario: Validation failure identifies the real prerequisite

- **WHEN** 依赖、模型资产、设备或推理步骤仍然不可用
- **THEN** 验证 SHALL 以非零状态退出，并报告具体失败阶段，而不是将模型加载错误伪装成空骨架结果

