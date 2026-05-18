## Context

The automatic court-line calibration capability already defines a local COCO segmentation dataset convention and has a backend validation script that checks COCO JSON structure, image references, categories, segmentation representations, and train/validation/test readiness. A real dataset is now present under `datasets/court-line-coco/` and the current validator reports it as structurally ready with 4,112 images, 4,106 polygon annotations, and no missing images.

That result is useful but incomplete for acceptance. The current dataset exposes both `Court` and `Court-Line` categories, while the observed annotations are assigned to `Court`. This means the team must distinguish whether the next model should train a court-region segmenter or a court-line segmenter before model-quality validation begins.

## Goals / Non-Goals

**Goals:**

- Make dataset acceptance repeatable and reviewable before model training.
- Separate structural readiness from target-category readiness.
- Report category usage, unused categories, and expected-target mismatches clearly.
- Surface likely split-leakage risks from image naming patterns before test metrics are trusted.
- Produce acceptance evidence that can be reused in project review: machine-readable summary, human-readable notes, and representative annotation previews.
- Keep all large data and generated artifacts local-only.

**Non-Goals:**

- Train or tune the court calibration model.
- Decide final model architecture or inference thresholds.
- Relabel the dataset automatically.
- Require a perfect leak-free dataset before experimentation; the goal is to make risk visible and actionable.
- Change production upload, calibration, or analysis APIs.

## Decisions

### Treat validation as two readiness layers

The validation workflow should expose `structural_ready` separately from `target_ready`. `structural_ready` answers whether the COCO dataset can be read and converted safely. `target_ready` answers whether the annotations match the intended training target, such as `Court`, `Court-Line`, or a configured one-class merge.

Alternatives considered:

- Keep a single `ready` flag: simpler, but it hides category-semantic issues and could allow a model to train on the wrong target.
- Fail the dataset whenever the configured target differs from observed labels: safer for strict training, but too rigid while the team is still deciding whether region segmentation or line segmentation is the better calibration source.

### Require explicit target-category intent

The acceptance workflow should require the developer to state the intended target category or target strategy. If the dataset contains `Court-Line` but no annotations use it, the report should call that out instead of silently mapping all annotations to `court_line`.

Alternatives considered:

- Infer the target from the first annotated category: convenient, but dangerous when exported COCO categories include unused classes.
- Always merge all categories into one class: useful for MVP YOLO conversion, but it blurs the difference between court-region and court-line segmentation in acceptance evidence.

### Add split-leakage diagnostics as warnings first

The dataset appears to use frame-derived names and Roboflow-style augmented suffixes. The validator should summarize suspicious source overlap across splits using normalized filenames or source tokens, but this should begin as a warning rather than a hard failure.

Alternatives considered:

- Ignore leakage until model training: faster, but validation metrics can be misleading if near-duplicate frames cross splits.
- Make any source overlap fail validation: too strict without confirmed source-video metadata, and it may block useful prototype work.

### Separate evidence generation from heavy training dependencies

Dataset acceptance evidence should rely on lightweight Python/OpenCV-style tooling and existing dataset files. It should not require Ultralytics training, CUDA, model weights, or runtime API startup.

Alternatives considered:

- Generate evidence only after YOLO conversion: aligns with training, but pushes semantic validation too late.
- Use frontend-only screenshots: good for presentation, but not enough for repeatable CI/local validation.

## Risks / Trade-offs

- Category names may not fully describe annotation semantics -> Mitigation: include representative overlay previews and require a documented target decision.
- Filename-based leakage detection may produce false positives or miss true source overlap -> Mitigation: treat it as a diagnostic and prefer source metadata when available later.
- Existing conversion maps all COCO categories into one class -> Mitigation: keep conversion behavior explicit and require acceptance output to record which categories were actually merged.
- Visual sample previews can grow into bulky artifacts -> Mitigation: write them to ignored local evidence paths and keep only summary docs in Git.
- The dataset can be structurally valid while still inadequate for real-world scenes -> Mitigation: record scene coverage and known gaps as part of acceptance notes.

## Migration Plan

- Extend or document the validation workflow without changing the dataset layout.
- Run the acceptance workflow on the current `datasets/court-line-coco/` dataset to establish a baseline.
- Record the target decision before starting `validate-court-line-model-quality`.
- If the target decision changes later, rerun dataset acceptance and update the evidence instead of reusing stale readiness claims.

## Open Questions

- Should the first model target be `Court` region segmentation, `Court-Line` line segmentation, or a one-class merged mask?
- Do the current image filenames preserve enough source-video information to detect split leakage reliably?
- Should acceptance require a small manually reviewed sample list per split before the first official model-quality run?
