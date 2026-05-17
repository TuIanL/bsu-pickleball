# Automatic Court-Line Calibration

This project can train a court-line segmentation model from a local COCO
segmentation dataset and use the trained model to propose semi-automatic court
calibration for uploaded pickleball videos.

## Local Dataset Layout

Use this default path when storing data inside the workspace:

```text
datasets/court-line-coco/
  train/
    *.jpg
    _annotations.coco.json
  valid/
    *.jpg
    _annotations.coco.json
  test/
    *.jpg
    _annotations.coco.json
```

Roboflow COCO exports commonly use `valid/` instead of `val/`; the validator
accepts both names.

You can also keep the dataset outside the repo and pass an absolute path to the
scripts. Dataset folders, converted labels, training runs, and model weights are
ignored by Git.

## Validate COCO Segmentation

```bash
cd backend
python scripts/validate_coco_segmentation.py \
  --dataset-root ../datasets/court-line-coco
```

The validator checks image references, category IDs, polygon/RLE segmentation
records, missing files, and train/validation/test readiness. Use it before
training so broken annotation paths are caught early.

## Prepare and Train

For a dry run that validates the dataset and writes a YOLO segmentation dataset:

```bash
cd backend
python scripts/train_court_line_segmentation.py \
  --dataset-root ../datasets/court-line-coco \
  --converted-output ../datasets/court-line-yolo \
  --prepare-only
```

To train with Ultralytics:

```bash
cd backend
python scripts/train_court_line_segmentation.py \
  --dataset-root ../datasets/court-line-coco \
  --converted-output ../datasets/court-line-yolo \
  --model yolo11n-seg.pt \
  --imgsz 1280 \
  --epochs 100
```

Thin painted lines are easy to lose at small input sizes, so start with
`--imgsz 960` or `--imgsz 1280`. Use source-aware train/val/test splits when
possible; splitting near-duplicate frames from one video across train and val
will make validation metrics look better than real deployment quality.

## Runtime Model

Place the selected model weight under:

```text
models/court-line/best.pt
```

Then start the backend with:

```bash
PICKLEBALL_COURT_LINE_MODEL_PATH=../models/court-line/best.pt
```

The automatic calibration API degrades to an unavailable result when no model is
configured, so manual calibration remains available.
