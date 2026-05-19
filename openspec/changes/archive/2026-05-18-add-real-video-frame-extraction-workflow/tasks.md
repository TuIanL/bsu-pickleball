## 1. Frame Extraction Core

- [x] 1.1 Add a reusable backend utility for opening a video with OpenCV, reading FPS/frame metadata, seeking by timestamp, and writing sampled JPEG frames.
- [x] 1.2 Implement interval-based sampling with `start`, `end`, and `max frames per video` controls.
- [x] 1.3 Generate sanitized per-video output folders and stable frame filenames containing video stem, frame index, and timestamp.
- [x] 1.4 Produce a JSON manifest with extraction settings, source video metadata, written frame records, and per-video errors.

## 2. Command-Line Workflow

- [x] 2.1 Add a backend script entry point for extracting frames from a single video file or a directory of supported video files.
- [x] 2.2 Add CLI arguments for input path, output path, interval seconds, max frames per video, start timestamp, end timestamp, JPEG quality, and overwrite behavior.
- [x] 2.3 Ensure unreadable videos and invalid sampling options produce clear diagnostics and non-success exit codes when appropriate.

## 3. Tests

- [x] 3.1 Add tests that create a small synthetic video and verify interval sampling, max-frame limiting, timestamp filtering, and manifest contents.
- [x] 3.2 Add tests for directory input, per-video output folders, stable filename format, and unreadable/missing video diagnostics.
- [x] 3.3 Run targeted backend tests for the new extraction workflow.

## 4. Documentation

- [x] 4.1 Update the court calibration guide with the real-video-to-frame-pool workflow, including recommended defaults and ignored local paths.
- [x] 4.2 Document that extracted frames are pending annotation assets and that the first real-scene adaptation target is manual `Court` region labeling.
- [x] 4.3 Document source-aware split guidance so real videos reserved for validation or test are not also used in training.

## 5. Verification

- [x] 5.1 Validate the OpenSpec change artifacts.
- [x] 5.2 Confirm the documented example commands match the implemented CLI arguments.
