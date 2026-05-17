## ADDED Requirements

### Requirement: Local COCO segmentation dataset convention
The system SHALL document and support a local COCO segmentation dataset convention for court-line training data without requiring large dataset files to be committed to version control.

#### Scenario: Developer prepares a local court-line dataset
- **WHEN** a developer places a COCO segmentation dataset under the documented court-line dataset path or configures an equivalent local path
- **THEN** the system provides enough documentation and ignored storage conventions for images, annotations, validation summaries, and training outputs to remain local-only

#### Scenario: Dataset files are present in the workspace
- **WHEN** court-line dataset images, annotations, or generated training runs exist locally
- **THEN** those large files are excluded from Git by project ignore rules or documented external-path guidance

### Requirement: COCO segmentation dataset validation
The system SHALL provide a developer workflow that validates the court-line COCO segmentation dataset before training.

#### Scenario: Developer validates a supported dataset
- **WHEN** the dataset contains readable images, COCO annotation JSON, segmentation annotations, image references, categories, and split metadata or split folders
- **THEN** the validation workflow reports image counts, annotation counts, category names, segmentation representation types, missing-file checks, and train/validation/test readiness

#### Scenario: Dataset has invalid or incomplete annotations
- **WHEN** the dataset references missing images, empty segmentations, malformed polygons, unsupported RLE records, or unknown categories
- **THEN** the validation workflow exits with a clear diagnostic and does not produce a successful training configuration

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
