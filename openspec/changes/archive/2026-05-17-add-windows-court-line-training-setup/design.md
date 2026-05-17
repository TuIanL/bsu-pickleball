## Context

The repository already contains a court-line COCO validation and YOLO segmentation training path, with local datasets and model weights ignored by Git. The current docs explain the dataset layout and basic training command, but a Windows 11 collaborator with an NVIDIA GPU still needs to know how to install CUDA-enabled PyTorch, create the backend virtual environment, receive the ignored dataset, avoid stale absolute paths in generated YOLO YAML, and run the training script with `cuda:0`.

The intended user is a teammate who clones the project onto Windows and contributes GPU training time. They should not need to understand the whole FastAPI or frontend runtime to begin training.

## Goals / Non-Goals

**Goals:**

- Provide a Windows-specific, copyable setup path for court-line segmentation training on NVIDIA hardware.
- Make CUDA verification explicit before training so slow CPU fallback is caught early.
- Keep dataset transfer and regeneration clear: source COCO data is copied locally, converted YOLO data is regenerated per machine, and generated training runs remain ignored.
- Provide a PowerShell helper script that handles the mechanical path and command differences on Windows.
- Keep the helper safe by validating prerequisites and failing clearly when CUDA, Python, or dataset paths are not ready.

**Non-Goals:**

- Installing or managing NVIDIA drivers outside Python.
- Bundling PyTorch CUDA wheels, datasets, trained weights, or model run artifacts in Git.
- Changing the training algorithm, model architecture, default dataset conversion behavior, or runtime automatic calibration API.
- Making the macOS/Linux startup scripts cross-platform in this change.
- Installing optional RTMPose/MMPose dependencies as part of court-line segmentation training.

## Decisions

### Document a two-layer setup: machine prerequisites first, project setup second

The Windows guide should first ask the collaborator to confirm NVIDIA driver visibility with `nvidia-smi`, then create the backend virtual environment and install CUDA-enabled PyTorch using the current official PyTorch selector command.

Alternative considered: bake a specific CUDA wheel URL into the repository. That would be convenient short-term, but it becomes stale as PyTorch and CUDA wheel support changes and may mismatch a teammate's driver.

### Install PyTorch before generic requirements

The helper should support a `-TorchInstallCommand` parameter so the user can paste the command from the official PyTorch selector before installing project requirements. This reduces the chance that `pip install -r requirements.txt` or Ultralytics pulls a CPU-only or otherwise unsuitable torch build.

Alternative considered: let `ultralytics` resolve PyTorch implicitly. That is simpler, but hides the most important performance dependency and can leave training on CPU.

### Regenerate YOLO-format data on Windows

The existing generated `datasets/court-line-yolo/court-line-seg.yaml` can contain absolute paths from the machine where conversion was run. The Windows workflow should treat `datasets/court-line-coco/` as the transferable source and regenerate `datasets/court-line-yolo/` locally.

Alternative considered: copy the already converted YOLO dataset. That can work if paths are repaired, but regenerating from COCO is deterministic and avoids confusing path mismatches.

### Keep RTMPose out of the training script

Court-line segmentation training requires Ultralytics/YOLO and PyTorch, not the optional RTMPose stack. The Windows training helper should not install OpenMMLab dependencies unless a future workflow explicitly asks for pose inference validation.

Alternative considered: make one full Windows setup script for the entire app. That would be broader than the immediate need and would mix training setup with heavier, more fragile pose runtime setup.

## Risks / Trade-offs

- [Risk] Official PyTorch install commands change over time. Mitigation: document that the user should copy the current Windows/Pip/CUDA command from the official selector and pass it to the script rather than relying on a hard-coded command.
- [Risk] Some Windows machines block PowerShell scripts. Mitigation: document the one-session `Set-ExecutionPolicy -Scope Process Bypass` pattern or direct script invocation guidance.
- [Risk] CUDA may be invisible even with an NVIDIA GPU because of driver or wheel mismatch. Mitigation: make `torch.cuda.is_available()` verification an explicit script step and fail before a long CPU training run unless CPU mode is requested.
- [Risk] Dataset archives can be placed in the wrong folder. Mitigation: document the exact `datasets/court-line-coco/train|valid|test` layout and have the helper run the existing validation script.
- [Risk] Auto batch sizing may still exceed GPU memory at `imgsz 1280`. Mitigation: document an initial `imgsz 960` smoke run and allow the script to pass batch/image-size parameters.

## Migration Plan

1. Add the Windows training documentation and PowerShell helper.
2. Verify the helper's argument parsing and non-training paths from the local repository where possible.
3. Ask the Windows collaborator to run the CUDA verification and `--prepare-only` path before starting full training.
4. If the helper causes trouble, fall back to the documented manual PowerShell commands; no runtime code or data migration is involved.

## Open Questions

- Which CUDA wheel command should the collaborator use on her machine after checking current PyTorch support and installed NVIDIA driver?
- Should the first full training run use `imgsz 960` for a safe GPU-memory baseline or go directly to `1280` for thin-line quality?
- How will the ignored source dataset be transferred: compressed archive, external drive, or cloud share?
