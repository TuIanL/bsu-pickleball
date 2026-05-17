## Why

The current real-video analysis flow depends on manual four-corner court calibration before player footpoints can be projected into court coordinates. A COCO segmentation dataset with thousands of labeled court-line images creates an opportunity to train a court-line model that can propose calibration automatically and reduce setup friction for real uploaded videos.

## What Changes

- Add an automatic court-line calibration capability backed by a COCO segmentation dataset, a trainable segmentation model, and local model asset conventions.
- Add a model inference path that predicts court-line masks from representative frames and converts those masks into ordered court keypoints.
- Add geometry validation that turns detected court keypoints into the existing homography-based calibration record when confidence and quality thresholds pass.
- Preserve manual calibration as the fallback and allow semi-automatic results to be reviewed or corrected before starting a real analysis job.
- Document local dataset placement and keep large datasets, training runs, and model weights out of version control.

## Capabilities

### New Capabilities

- `automatic-court-line-calibration`: Dataset, training, inference, post-processing, and API behavior for deriving court calibration from COCO segmentation court-line labels.

### Modified Capabilities

- `video-analysis-job-flow`: The upload/calibration handoff can use an automatic calibration suggestion before job creation, while preserving manual calibration and limited-analysis fallbacks.

## Impact

- Backend vision: new court-line segmentation adapter and mask-to-keypoints post-processing under the CourtVision Calibration Engine boundary.
- Backend APIs and schemas: automatic calibration request/response models, quality diagnostics, preview artifacts, and integration with existing calibration storage.
- Backend scripts/docs: COCO dataset validation/conversion guidance, training commands, model placement, and dataset ignore rules.
- Frontend workflow: calibration step can request an automatic suggestion, show confidence/preview, and let the user accept or manually correct the result.
- Storage and configuration: local `datasets/` conventions, ignored training artifacts, and model weight path configuration for the trained court-line model.
