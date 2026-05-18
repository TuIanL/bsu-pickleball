## Why

The project already has a local COCO segmentation dataset and a structural validation script, but dataset readiness for court-line calibration is still ambiguous because structural validity does not prove that the annotations match the intended training target. Before model-quality validation starts, the team needs a repeatable acceptance workflow that separates "COCO dataset is readable" from "dataset is semantically ready to train the court-line or court-region model."

## What Changes

- Strengthen dataset validation acceptance for local COCO segmentation data used by automatic court calibration.
- Require validation output to distinguish structural readiness from target-category readiness.
- Require category-usage diagnostics so unused categories, mislabeled categories, and ambiguous training targets are visible before training.
- Require split-leakage diagnostics that surface likely source-frame or source-video overlap across train, validation, and test splits.
- Define acceptance evidence expected for project review: summary JSON, split/category statistics, target decision, and representative annotation visualizations.
- Preserve the existing local-only dataset convention and keep large datasets, converted labels, training runs, and model weights out of version control.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `automatic-court-line-calibration`: Expand dataset validation requirements from basic COCO structural validation to full dataset acceptance, including target-category readiness, category usage, split-leakage risk, and review evidence.

## Impact

- Backend dataset validation workflow under the CourtVision Calibration Engine.
- Dataset documentation under `datasets/` and automatic court calibration docs.
- Local developer acceptance evidence for the existing `datasets/court-line-coco/` dataset.
- No production API contract changes and no training/runtime dependency changes.
