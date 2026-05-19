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
The system SHALL expose actionable automatic court-line calibration diagnostics in the upload workflow for available, unavailable, rejected, and failed attempts.

#### Scenario: Automatic calibration is available
- **WHEN** automatic court-line calibration returns an available suggestion
- **THEN** the upload workflow displays the confidence, selected frame reference, keypoint fill status, preview when available, and calibration quality diagnostics when returned

#### Scenario: Automatic calibration model is unavailable
- **WHEN** automatic court-line calibration returns unavailable because the model path is unset, missing, or cannot be loaded
- **THEN** the upload workflow displays that model availability diagnosis, including configured model path when returned, and keeps manual four-corner calibration available

#### Scenario: Automatic calibration geometry is rejected
- **WHEN** automatic court-line calibration returns rejected because the mask or fitted geometry fails validation
- **THEN** the upload workflow displays the backend rejection detail, mask confidence, mask area ratio, line count, selected frame reference, and preview when available

#### Scenario: Automatic calibration request fails
- **WHEN** the automatic calibration request fails with an HTTP or network error
- **THEN** the upload workflow displays the request failure status and backend detail when available while preserving the selected video, metadata, and manual calibration controls

#### Scenario: Older automatic calibration response lacks diagnostics
- **WHEN** the frontend receives an automatic calibration response without optional diagnostic fields
- **THEN** the upload workflow remains stable and displays a concise unavailable diagnostic without crashing

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

