## Context

The existing court calibration workflow already supports local COCO segmentation validation, YOLO segmentation training, runtime model loading, and automatic calibration previews. The current local dataset is mostly online match imagery and does not represent the team's real phone/tripod footage, so the next useful data step is to sample real videos into a frame pool for manual `Court` region annotation.

The workflow should stay local-first because videos, extracted frames, and annotation exports are large and should remain outside Git. The near-term user is a developer or dataset curator preparing real-court frames for tools such as Roboflow, CVAT, or Label Studio before exporting COCO segmentation annotations.

## Goals / Non-Goals

**Goals:**

- Provide a repeatable backend-local command that extracts annotation-ready JPEG frames from one video file or a directory of videos.
- Support MVP A+B controls: sampling interval, maximum frames per video, optional start/end timestamps, per-video output folders, stable file naming, and manifest output.
- Preserve enough source metadata to audit where each frame came from and to avoid source leakage when splitting annotated data.
- Document that extracted frames are a pending annotation pool and that the immediate annotation target is `Court`.
- Keep the workflow compatible with the existing COCO validation and training pipeline once annotations are exported.

**Non-Goals:**

- No frontend UI for video-to-frame extraction in this change.
- No automatic `Court` annotation, weak labeling, or model-assisted annotation.
- No perceptual-hash or image-similarity deduplication in the first implementation.
- No direct conversion from extracted frames to train-ready COCO without human annotations.
- No changes to runtime automatic calibration inference behavior.

## Decisions

### Decision: Build a local CLI script first

Create a backend script, likely `backend/scripts/extract_real_video_frames.py`, rather than a frontend workflow.

Rationale: dataset preparation is a local developer operation, and the existing court calibration training workflow already lives under backend scripts. A CLI keeps the first implementation small, reviewable, and easy to run on whichever machine stores the raw videos.

Alternative considered: add a web upload/extract UI. This was deferred because it adds file-management, progress, and storage concerns before the data workflow is proven useful.

### Decision: Output a frame pool, not a COCO dataset

The extractor writes JPEG frames and a manifest under an ignored local path such as `datasets/real-court-frame-pool/<video-stem>/`. It does not generate `_annotations.coco.json`.

Rationale: unannotated frames are not training data. Separating frame extraction from annotation export prevents unlabeled or mislabeled real frames from being accidentally mixed into model training.

Alternative considered: generate an empty COCO scaffold. This was deferred because many annotation tools create their own project/export format, and empty COCO files can look more train-ready than they are.

### Decision: Use time-based sampling with an explicit maximum

The CLI supports interval sampling, for example one frame every 1-2 seconds, and a `--max-frames-per-video` limit. Optional start/end timestamps let users skip warmup, setup, or irrelevant footage.

Rationale: real videos contain many near-duplicate adjacent frames. Interval plus maximum count gives users predictable coverage without creating thousands of redundant images from one camera angle.

Alternative considered: extract every Nth frame. This is useful internally, but a time interval is easier for users to reason about across videos with different FPS.

### Decision: Keep per-video folders and source-aware names

Each video gets its own output subfolder. Filenames include sanitized video stem, frame index, and timestamp. The manifest repeats the source path, output path, frame index, timestamp, width, height, FPS, and extraction settings.

Rationale: the downstream dataset split must avoid putting frames from the same source video into both train and validation/test. Per-video organization and manifest metadata make that visible even after frames are moved into annotation tools.

Alternative considered: write all frames into one flat folder. This is convenient for upload, but it hides source grouping and increases leakage risk.

### Decision: Document `Court` as the immediate annotation target

The existing dataset has effective `Court` annotations and zero used `Court-Line` annotations. The new workflow should tell curators to mark the visible playable court region or outer court region as `Court` for short-term domain adaptation.

Rationale: the automatic calibration pipeline ultimately needs a stable court quadrilateral/homography. For real-scene adaptation, `Court` region masks are faster and likely more robust than thin white-line masks as a first iteration.

Alternative considered: switch fully to `Court-Line`. This remains valuable later, but it requires more precise annotation and may be harder in blurry or occluded real footage.

## Risks / Trade-offs

- Repeated frames still inflate the dataset if intervals are too dense -> Mitigate with a documented default interval, a maximum per video, and source-aware splitting guidance.
- `Court` region masks may not match line-based post-processing perfectly -> Mitigate by documenting the target choice and preserving room for later `Court-Line` or keypoint-specific improvements.
- Annotation tools may rename files or flatten folders -> Mitigate by generating a manifest and embedding source metadata in stable filenames.
- Extracted frames may include motion blur, occlusion, or irrelevant footage -> Mitigate with start/end controls and a future path for manual review or quality filtering.
- Large local frame pools may consume disk space -> Mitigate by keeping outputs under ignored dataset paths and making limits explicit.

## Migration Plan

1. Add the frame extraction script and tests.
2. Document the real-video-to-frame-pool workflow in the court calibration guide.
3. Use the script to sample a small real footage set, manually annotate `Court`, export COCO, then validate with the existing COCO validator.
4. Fine-tune from the current court model only after the real-scene validation split is held out by source video.

Rollback is simply to stop using the new script and remove local generated frame pools; no persisted application data or runtime APIs are changed.

## Open Questions

- Which real videos should be reserved as the first source-held-out test set before any fine-tuning?
- Should the first annotation guide define `Court` as the full visible court surface, only the pickleball boundary, or the playable quadrilateral when parts are occluded?
- After the first fine-tune, should the post-processing continue using contour fallback for `Court` masks or be adjusted to prefer region-derived quadrilaterals?
