## Why

Court-line segmentation training is already supported by the backend, but the current setup guidance is oriented toward macOS/Linux-style shells and does not give a Windows 11 + NVIDIA collaborator a reliable path from a fresh clone to CUDA-backed training. The dataset and generated YOLO paths are intentionally ignored by Git, so a colleague cannot simply clone the repository and start training without extra environment and data-transfer instructions.

## What Changes

- Add Windows 11 + NVIDIA training documentation for court-line segmentation, including Python, virtual environment, CUDA-enabled PyTorch, Ultralytics, dataset placement, validation, training, and runtime model placement.
- Add a PowerShell helper script that can create or reuse the backend virtual environment, install dependencies in the correct order, verify CUDA visibility, validate/prepare the local dataset, and optionally start training.
- Document how ignored local assets move between machines, especially `datasets/court-line-coco/`, regenerated `datasets/court-line-yolo/`, ignored `runs/`, and selected `models/court-line/best.pt`.
- Preserve the existing Python training implementation and backend runtime behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `automatic-court-line-calibration`: Extend the documented court-line segmentation training workflow with Windows 11 + NVIDIA setup guidance and a repeatable PowerShell helper for CUDA-backed local training.

## Impact

- Adds documentation under the existing court-line calibration/training docs.
- Adds a Windows PowerShell script under project scripts for collaborator onboarding.
- May mention current PyTorch CUDA installation guidance but does not vendor GPU libraries, datasets, model weights, or generated training artifacts.
- Does not change API contracts, frontend behavior, model inference, dataset conversion logic, or checked-in large assets.
