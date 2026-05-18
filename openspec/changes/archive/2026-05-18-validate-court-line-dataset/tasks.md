## 1. Validation Contract

- [x] 1.1 Extend the dataset validation report model to expose separate structural readiness and target-category readiness fields.
- [x] 1.2 Add a CLI option or equivalent configuration for declaring the intended target category or target strategy.
- [x] 1.3 Report category usage counts across each split and across the whole dataset.
- [x] 1.4 Report unused COCO categories separately from categories that contain annotations.

## 2. Target Readiness Diagnostics

- [x] 2.1 Detect when the intended target category has zero annotations and return a clear target mismatch diagnostic.
- [x] 2.2 Detect when annotations are present under a different category than the intended target and preserve structural readiness while marking target readiness as failed or pending.
- [x] 2.3 Record the current dataset baseline, including total images, annotations, split counts, segmentation type, observed categories, and unused categories.

## 3. Split Leakage Review

- [x] 3.1 Add source-token normalization for image filenames or source metadata to identify likely related frames across splits.
- [x] 3.2 Report split-leakage risk examples without treating the dataset as structurally unreadable.
- [x] 3.3 Document how developers should interpret leakage warnings before trusting validation/test metrics.

## 4. Acceptance Evidence

- [x] 4.1 Add or document a lightweight acceptance workflow that writes a machine-readable summary to an ignored local evidence path.
- [x] 4.2 Generate representative annotation preview artifacts for train, validation, and test samples in ignored local evidence paths.
- [x] 4.3 Document the required acceptance evidence for project review: summary JSON, split/category statistics, target decision state, preview artifacts, and known risks.

## 5. Verification

- [x] 5.1 Add tests for structural-ready and target-ready success cases.
- [x] 5.2 Add tests for unused categories and target-category mismatch diagnostics.
- [x] 5.3 Add tests for split-leakage warning output.
- [x] 5.4 Run the validation workflow against `datasets/court-line-coco/` and capture the resulting acceptance baseline.
- [x] 5.5 Run the relevant backend test suite for dataset validation and conversion.
