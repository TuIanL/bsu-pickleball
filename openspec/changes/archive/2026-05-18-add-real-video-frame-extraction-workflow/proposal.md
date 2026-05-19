## Why

The current court calibration training data is dominated by online match imagery, while the target runtime environment depends on real footage captured from the project team's own courts. We need a repeatable way to turn those real videos into a curated image pool for manual `Court` annotation so the segmentation model can adapt to the deployment domain.

## What Changes

- Add a local frame extraction workflow that accepts one video or a directory of videos and exports sampled JPEG frames for later annotation.
- Support MVP A+B controls: sampling interval, maximum frames per video, optional start/end timestamps, per-video output folders, stable frame naming, and a JSON manifest.
- Treat extracted frames as a "pending annotation" pool, not as a train-ready COCO dataset.
- Document the recommended `Court` region annotation path for near-term domain adaptation, including source-aware train/validation/test splitting after annotation export.
- Keep large source videos, extracted frames, annotation exports, and manifests in ignored local dataset paths.
- Exclude frontend upload UI, automatic annotation, perceptual-hash deduplication, and direct COCO generation from this change.

## Capabilities

### New Capabilities

- `real-video-frame-extraction`: Defines the local workflow for sampling real court videos into annotation-ready frame pools with manifest metadata and duplicate-risk controls.

### Modified Capabilities

- `automatic-court-line-calibration`: Clarifies that real-scene domain adaptation may use `Court` region annotations as the short-term target before or instead of strict `Court-Line` masks.

## Impact

- Adds a backend-local dataset preparation script and supporting tests around video frame sampling.
- Extends court calibration documentation with the real-video-to-`Court`-annotation workflow.
- Uses existing OpenCV dependency already required by the backend vision stack.
- Affects local ignored dataset conventions under `datasets/`; no committed videos, extracted frames, model weights, or training outputs.
