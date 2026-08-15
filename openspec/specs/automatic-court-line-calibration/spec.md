# automatic-court-line-calibration Specification

## Purpose
Defines the local dataset, training, inference, post-processing, persistence, and preview behavior for deriving pickleball court calibration from COCO segmentation court-line labels.
## Requirements
### Requirement: Local COCO segmentation dataset convention
The system SHALL document and support a local COCO segmentation dataset convention for court-line training data without requiring large dataset files to be committed to version control.

#### Scenario: Developer prepares a local court-line dataset
- **WHEN** a developer places a COCO segmentation dataset under the documented court-line dataset path or configures an equivalent local path
- **THEN** the system provides enough documentation and ignored storage conventions for images, annotations, validation summaries, and training outputs to remain local-only

#### Scenario: Dataset files are present in the workspace
- **WHEN** court-line dataset images, annotations, or generated training runs exist locally
- **THEN** those large files are excluded from Git by project ignore rules or documented external-path guidance

### Requirement: COCO segmentation dataset validation
The system SHALL provide a developer workflow that validates the court-line COCO segmentation dataset before training and reports both structural dataset readiness and target-category readiness for the intended calibration model.

#### Scenario: Developer validates a supported dataset
- **WHEN** the dataset contains readable images, COCO annotation JSON, segmentation annotations, image references, categories, and split metadata or split folders
- **THEN** the validation workflow reports image counts, annotation counts, category names, category usage counts, unused categories, segmentation representation types, missing-file checks, required split readiness, and overall structural readiness

#### Scenario: Dataset has invalid or incomplete annotations
- **WHEN** the dataset references missing images, empty segmentations, malformed polygons, unsupported RLE records, or unknown categories
- **THEN** the validation workflow exits with a clear diagnostic and does not produce a successful training configuration

#### Scenario: Dataset category usage does not match intended target
- **WHEN** the developer validates the dataset with an intended target category or target strategy and the observed annotation categories do not match that intent
- **THEN** the validation workflow reports target readiness as failed or pending and identifies the observed categories, unused categories, and mismatch reason without hiding structural readiness

#### Scenario: Dataset contains unused training categories
- **WHEN** the COCO category list includes a category that has zero annotations in all validated splits
- **THEN** the validation workflow reports that category as unused so the developer can distinguish exported label metadata from actual training labels

#### Scenario: Dataset may leak related frames across splits
- **WHEN** image names or source metadata indicate that likely related source frames, source videos, or duplicated augmented samples appear in more than one split
- **THEN** the validation workflow reports a split-leakage risk diagnostic with enough examples for review without treating the dataset as structurally unreadable

#### Scenario: Dataset acceptance evidence is generated
- **WHEN** the developer runs the dataset acceptance workflow for a local COCO dataset
- **THEN** the workflow produces reviewable evidence including a machine-readable summary, split/category statistics, the target-category decision state, and representative annotation preview artifacts stored in ignored local paths

### Requirement: Court-line segmentation training workflow
The system SHALL provide a repeatable local workflow for training and exporting a court-line segmentation model from the validated COCO segmentation dataset.

#### Scenario: Developer trains the court-line model
- **WHEN** a developer runs the documented training workflow with a valid dataset path and training configuration
- **THEN** the workflow trains a segmentation model for court-line detection and writes model weights, logs, metrics, and run artifacts to ignored local output paths

#### Scenario: Developer exports a trained model for runtime use
- **WHEN** a trained model checkpoint is selected for runtime inference
- **THEN** the workflow documents or places the runtime model artifact under the configured court-line model path without committing the weight file to Git

### Requirement: Court-line segmentation inference
The system SHALL run court-line segmentation on a representative video frame when a configured runtime model is available.

#### Scenario: Model produces a court-line mask
- **WHEN** the backend receives an automatic court calibration request for a readable uploaded video or frame and the court-line model is configured
- **THEN** the backend returns segmentation-derived mask diagnostics including frame size, selected frame reference, model confidence, and whether a usable court-line mask was produced

#### Scenario: Model is unavailable
- **WHEN** the backend receives an automatic court calibration request but the model path is unset, missing, or cannot be loaded
- **THEN** the backend returns a stable unavailable result that instructs the frontend to keep manual calibration available

### Requirement: Mask-to-court-keypoint post-processing
The system SHALL convert a predicted court-line mask into ordered standard court keypoints when the mask passes geometry validation.

#### Scenario: Mask supports a valid court quadrilateral
- **WHEN** the predicted mask contains enough line evidence to fit court boundary candidates and derive four ordered outer court corners
- **THEN** the backend returns `top_left`, `top_right`, `bottom_right`, and `bottom_left` image points with confidence and geometry quality diagnostics

#### Scenario: Mask cannot produce reliable keypoints
- **WHEN** the predicted mask is too sparse, fragmented, ambiguous, outside the frame bounds, or fails standard pickleball court geometry checks
- **THEN** the backend returns a rejected automatic calibration result and MUST NOT create a misleading accepted homography

### Requirement: Semi-automatic calibration persistence
The system SHALL create an existing-compatible calibration record from automatic keypoints only after the automatic result passes validation or is explicitly accepted with reviewable keypoints.

#### Scenario: Automatic result is accepted
- **WHEN** a user or client accepts a valid automatic court keypoint result for an uploaded video
- **THEN** the backend stores a calibration record with method `semi-automatic`, a homography, inverse homography, quality diagnostics, and the original image-to-court correspondences

#### Scenario: Automatic result needs manual correction
- **WHEN** an automatic suggestion is present but the user adjusts one or more keypoints before submission
- **THEN** the backend stores the corrected correspondences through the same calibration contract and preserves enough method or diagnostic detail to distinguish the result from fully manual calibration

### Requirement: Automatic calibration preview artifacts
The system SHALL provide visual preview artifacts that allow users and developers to inspect automatic court-line detection before analysis starts.

#### Scenario: Automatic preview is available
- **WHEN** automatic segmentation and keypoint post-processing complete for a representative frame
- **THEN** the backend exposes or records a preview artifact showing the selected frame, detected mask or fitted lines, ordered keypoints, and projected court overlay when a homography is available

#### Scenario: Preview cannot be generated
- **WHEN** OpenCV, frame access, or output storage prevents preview generation
- **THEN** the backend returns a clear diagnostic while preserving the structured automatic calibration result status

### Requirement: Windows CUDA training setup
The system SHALL document and support a Windows 11 + NVIDIA setup path for local court-line segmentation training without requiring datasets, generated YOLO data, training runs, or model weights to be committed to version control.

#### Scenario: Collaborator prepares Windows training environment
- **WHEN** a Windows 11 collaborator clones the repository for court-line segmentation training
- **THEN** the documentation provides Windows PowerShell commands for creating the backend Python environment, installing CUDA-enabled PyTorch and project training dependencies, verifying CUDA visibility, and validating the local dataset before training

#### Scenario: Collaborator transfers ignored dataset assets
- **WHEN** the source COCO court-line dataset is copied from another machine
- **THEN** the documentation identifies the required local `datasets/court-line-coco/` layout and explains that generated `datasets/court-line-yolo/` files should be regenerated on the Windows machine

### Requirement: Windows court-line training helper
The system SHALL provide a PowerShell helper that runs the Windows court-line segmentation setup and training workflow with explicit CUDA verification.

#### Scenario: Helper prepares and validates dataset
- **WHEN** the collaborator runs the helper with a valid dataset path and prepare-only mode
- **THEN** the helper creates or reuses the backend virtual environment, installs required dependencies, checks PyTorch CUDA availability unless CPU mode is explicitly selected, validates the COCO dataset, and prepares the YOLO segmentation dataset

#### Scenario: Helper starts GPU training
- **WHEN** the collaborator runs the helper with training enabled and `cuda:0` selected
- **THEN** the helper invokes the existing court-line training script with the configured dataset path, converted dataset path, model, image size, epoch count, batch setting, project output path, run name, and CUDA device

#### Scenario: CUDA is unavailable
- **WHEN** the helper is configured for CUDA training but PyTorch reports that CUDA is unavailable
- **THEN** the helper fails before starting model training and prints a clear diagnostic that points to PyTorch/CUDA installation or NVIDIA driver setup

### Requirement: User-facing automatic calibration diagnostics

系统 SHALL 在 upload workflow 中为 available / unavailable / rejected / failed 的自动球场线标定尝试暴露可操作的诊断信息。开发诊断细节（confidence、模型信息、Mask 统计、选中帧、preview 等）SHALL 默认折叠隐藏，仅通过标题旁 Info (i) 图标展开，避免干扰用户聚焦可拖拽四边形主画面；识别中进度与失败/拒绝的操作指引 SHALL 保持默认可见，不进折叠。

#### Scenario: Automatic calibration is available

- **WHEN** automatic court-line calibration returns an available suggestion
- **THEN** the upload workflow SHALL 默认仅显示主画面与已自动铺设的可拖拽四边形
- **AND** 开发诊断细节（confidence、selected frame reference、keypoint fill status、preview、calibration quality diagnostics）SHALL 折叠隐藏
- **AND** 用户点击标题旁 Info (i) 图标后 SHALL 展开显示上述诊断细节，再次点击 SHALL 收起

#### Scenario: 自动标定进行中显示进度

- **WHEN** 自动标定请求处于上传或识别中（uploading / detecting）
- **THEN** the upload workflow SHALL 默认可见地显示「正在自动识别球场边线…」进度文本
- **AND** 该进度文本 SHALL NOT 被折叠隐藏

#### Scenario: Automatic calibration model is unavailable

- **WHEN** automatic court-line calibration returns unavailable because the model path is unset, missing, or cannot be loaded
- **THEN** the upload workflow SHALL 默认可见地显示模型不可用诊断（包括返回的 configured model path）与人工标定可用指引
- **AND** manual four-corner calibration SHALL 保持可用

#### Scenario: Automatic calibration geometry is rejected

- **WHEN** automatic court-line calibration returns rejected because the mask or fitted geometry fails validation
- **THEN** the upload workflow SHALL 默认可见地显示拒绝指引（提示用户手动拖动或调整标定帧）
- **AND** 用户点击 Info (i) 图标后 SHALL 展开显示 rejection detail、mask confidence、mask area ratio、line count、selected frame reference、preview 等诊断详情

#### Scenario: Automatic calibration request fails

- **WHEN** the automatic calibration request fails with an HTTP or network error
- **THEN** the upload workflow SHALL 默认可见地显示 request failure 状态与可用的后端 detail
- **AND** 系统 SHALL 保留 selected video、metadata 与 manual calibration controls

#### Scenario: Older automatic calibration response lacks diagnostics

- **WHEN** the frontend receives an automatic calibration response without optional diagnostic fields
- **THEN** the upload workflow SHALL 保持稳定，默认显示 concise unavailable 诊断且不崩溃
- **AND** Info (i) 图标 SHALL 在无任何诊断数据时不渲染或不可展开

#### Scenario: 诊断区默认折叠且不持久化

- **WHEN** 用户进入场地标定步骤且自动标定已有结果
- **THEN** 开发诊断区 SHALL 默认处于折叠态
- **AND** 每次进入标定（组件随 videoId 重置）SHALL 重置为折叠态，不持久化展开状态

### Requirement: Real-scene Court region adaptation dataset
The system SHALL document and support using manually annotated `Court` region masks from real captured footage as a short-term domain adaptation path for automatic court calibration training.

#### Scenario: Developer chooses Court region target
- **WHEN** a developer prepares real captured frames for near-term court calibration adaptation
- **THEN** the workflow identifies `Court` as the intended manual segmentation category and distinguishes it from strict `Court-Line` annotation

#### Scenario: Developer validates real Court annotations
- **WHEN** a developer exports the annotated real footage frames as a COCO segmentation dataset
- **THEN** the existing dataset validation workflow can be run with `Court` as the target category or with an explicit merge strategy when combining compatible court-region categories

#### Scenario: Developer mixes online and real footage datasets
- **WHEN** online match imagery and real captured footage are combined for training or fine-tuning
- **THEN** the workflow documents that validation and test splits should be source-aware and should reserve real captured videos for evaluating deployment-domain performance

### Requirement: Calibration enforces baseline Y monotonicity
The manual court calibration page SHALL validate that the two near-baseline corner points have larger image Y than the two far-baseline corner points, and SHALL warn the user when the baseline order appears reversed.

#### Scenario: Calibration baselines are in expected order
- **WHEN** the user finishes selecting four court corners
- **THEN** the calibration page SHALL compute the average image Y of the two far-baseline corners and the two near-baseline corners
- **AND** if `near_baseline_avg_y - far_baseline_avg_y` is greater than a reasonable threshold, the page SHALL accept the calibration without further prompt

#### Scenario: Calibration baselines appear reversed
- **WHEN** the user finishes selecting four court corners
- **AND** the near-baseline average image Y is less than the far-baseline average image Y (or the difference is below the threshold)
- **THEN** the calibration page SHALL surface a confirmation prompt such as "近端与远端底线可能颠倒，请确认画面顶/底对应的场地底线"
- **AND** the user MAY proceed with the calibration after confirming

#### Scenario: Calibration Y values are missing or non-finite
- **WHEN** one or more of the four corner image Y values are not finite
- **THEN** the calibration page SHALL treat the order check as inconclusive and proceed without prompting

### Requirement: 自动标定进入即触发

系统 SHALL 在场地标定组件挂载且视频已就绪后自动发起一次自动球场标定请求，无需用户手动点击触发；自动标定成功后 SHALL 将返回的四角点铺设成可拖拽四边形，失败或拒绝时 SHALL 提示用户并保留人工标定兜底。

#### Scenario: 自动标定请求自动发起

- **WHEN** 用户进入场地标定步骤且对应的视频已注册（`videoId` 就绪）
- **THEN** 系统自动调用一次自动标定请求
- **AND** 界面显示"识别中"等进度状态，而非要求用户先点击触发按钮

#### Scenario: 自动标定可用并铺设四边形

- **WHEN** 自动标定返回 `available` 且包含四个角点
- **THEN** 系统将四个角点铺设成可拖拽四边形
- **AND** 显示置信度、选中帧信息与预览（可用时）
- **AND** 用户可直接确认进入下一步，或在此基础上拖拽修正

#### Scenario: 自动标定失败或拒绝

- **WHEN** 自动标定返回 `rejected`、`unavailable`，或请求发生 HTTP/网络错误
- **THEN** 系统提示"标定失败"及可用的后端诊断信息
- **AND** 保留人工标定（可拖拽四边形）作为兜底，用户仍可完成标定

#### Scenario: 用户重新触发自动标定

- **WHEN** 自动标定已失败或用户希望重新识别
- **THEN** 系统提供"重新自动识别"操作，允许用户手动再次发起自动标定请求

### Requirement: 自动标定抽帧位置固定靠前

自动标定抽帧 SHALL 使用靠近视频开头固定位置抽帧，而非按 10% 时长比例定位；开头为黑场或过渡帧时 SHALL 可向后小步前跳以取到可用画面。

#### Scenario: 按靠近开头位置抽帧

- **WHEN** 自动标定发起且未显式指定抽帧位置
- **THEN** 后端在靠近视频开头固定位置（如第 2~3 帧或约 0.5 秒处）抽取标定帧

#### Scenario: 开头为黑场或过渡帧

- **WHEN** 固定靠前位置抽到的是黑场或不可用过渡帧
- **THEN** 自动标定可能被拒绝
- **AND** 系统提示"标定失败"并回退人工标定（人工路径的视频抽帧仍会向后小步前跳以跳过黑场）

### Requirement: 标定四边形拖拽交互

手动/半自动标定界面 SHALL 以可拖拽四边形呈现四个角点，支持拖动四角与四条边；提交时 SHALL 仍回传四个角点的图像坐标，后端契约不变。

#### Scenario: 拖动角点

- **WHEN** 用户拖动四边形的某个角点
- **THEN** 仅该角点的坐标更新，其余角点保持不变

#### Scenario: 拖动边

- **WHEN** 用户拖动四边形的某条边
- **THEN** 该边两个端点一起平移
- **AND** 平移后角点坐标 clamp 到画面范围内

#### Scenario: 自动结果铺设四边形

- **WHEN** 自动标定返回可用角点
- **THEN** 四个角点按固定顺序（top_left、top_right、bottom_right、bottom_left）铺设成四边形
- **AND** 用户可在此基础上拖拽角点或边进行修正

#### Scenario: 提交拖拽后的角点坐标

- **WHEN** 用户完成拖拽并确认提交
- **THEN** 系统回传四个角点的图像坐标
- **AND** 后端以与既有手工/半自动标定相同的契约创建标定记录

