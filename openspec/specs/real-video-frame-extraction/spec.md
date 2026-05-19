# real-video-frame-extraction Specification

## Purpose
TBD - created by archiving change add-real-video-frame-extraction-workflow. Update Purpose after archive.
## Requirements
### Requirement: Real court video frame extraction workflow
The system SHALL provide a local developer workflow that extracts annotation-ready still frames from real pickleball court videos without requiring source videos or extracted frames to be committed to version control.

#### Scenario: Developer extracts frames from one video
- **WHEN** a developer runs the frame extraction workflow with a readable video file, an output directory, a sampling interval, and a maximum frame count
- **THEN** the workflow writes sampled JPEG frames to an ignored local output path and reports how many frames were written for that video

#### Scenario: Developer extracts frames from a video directory
- **WHEN** a developer runs the frame extraction workflow with a directory containing supported video files
- **THEN** the workflow processes each supported video and writes extracted frames under per-video output folders

#### Scenario: Source video cannot be read
- **WHEN** the workflow receives a missing, unsupported, or unreadable video file
- **THEN** it fails or records the failure with a clear diagnostic that identifies the affected source video

### Requirement: Controlled sampling options
The system SHALL let developers control frame extraction volume and relevant footage windows so real videos do not produce excessive near-duplicate training candidates.

#### Scenario: Interval sampling is used
- **WHEN** a developer specifies a positive sampling interval in seconds
- **THEN** the workflow samples frames at approximately that wall-clock interval using the source video's timing metadata

#### Scenario: Maximum frame count is used
- **WHEN** a developer specifies a maximum number of frames per video
- **THEN** the workflow stops writing additional frames for that video after the maximum is reached

#### Scenario: Time window is used
- **WHEN** a developer specifies start and/or end timestamps
- **THEN** the workflow only writes frames whose timestamps fall inside the selected window

### Requirement: Source-aware frame organization and naming
The system SHALL organize extracted frames so downstream annotation and dataset splitting can preserve source-video provenance.

#### Scenario: Per-video output folder is created
- **WHEN** frames are extracted from a source video
- **THEN** the workflow writes them under a folder named from a sanitized source-video stem

#### Scenario: Stable frame filename is generated
- **WHEN** a frame is written
- **THEN** its filename includes the sanitized video stem, source frame index, and timestamp so the source moment remains identifiable after export or upload to annotation tools

### Requirement: Extraction manifest
The system SHALL write a machine-readable manifest for each extraction run so developers can audit frame provenance and extraction settings.

#### Scenario: Manifest is written
- **WHEN** the workflow completes an extraction run
- **THEN** it writes a JSON manifest containing source video path, output frame path, frame index, timestamp, video FPS when available, frame dimensions, sampling settings, and any per-video errors

#### Scenario: Manifest supports source-aware split review
- **WHEN** a developer reviews extracted frames before annotation or COCO export
- **THEN** the manifest provides enough source-video grouping information to avoid placing related frames from the same source video into both train and validation or test splits

### Requirement: Pending annotation dataset boundary
The system SHALL treat extracted real-video frames as a pending annotation pool rather than a train-ready COCO segmentation dataset.

#### Scenario: Frames are extracted before annotation
- **WHEN** the frame extraction workflow writes frames to the local frame pool
- **THEN** it does not create train/validation/test COCO annotation files or represent the frames as ready for training

#### Scenario: Developer prepares annotations after extraction
- **WHEN** extracted frames are imported into an annotation tool
- **THEN** the documented workflow identifies manual `Court` region labeling and COCO segmentation export as the next step before using the existing dataset validator and training scripts

