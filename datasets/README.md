# Local Court-Line Datasets

Large training datasets stay local and are ignored by Git. Put the COCO
segmentation dataset for automatic court-line calibration here when you are
ready to train:

```text
datasets/
  court-line-coco/
    train/
      frame-0001.jpg
      _annotations.coco.json
    valid/
      frame-1001.jpg
      _annotations.coco.json
    test/
      frame-2001.jpg
      _annotations.coco.json
```

An external path is also fine. Pass it to the validation and training scripts
with `--dataset-root /absolute/path/to/court-line-coco`.

Generated YOLO-format datasets, training runs, caches, and model checkpoints
should remain local. Runtime model weights belong under `models/court-line/`,
which is also ignored by Git.

For acceptance evidence, write validation summaries and annotation previews to
an ignored local subdirectory such as:

```text
datasets/court-line-coco/acceptance/
  summary.json
  previews/
    train-*.jpg
    val-*.jpg
    test-*.jpg
```

Use this evidence to record whether the dataset is structurally valid, which
categories are actually annotated, whether the intended target category is ready,
and whether split-leakage warnings need review before model metrics are trusted.
