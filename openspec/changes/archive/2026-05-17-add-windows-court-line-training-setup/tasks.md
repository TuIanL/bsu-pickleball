## 1. Windows Training Documentation

- [x] 1.1 Update court-line calibration documentation with a Windows 11 + NVIDIA setup section covering driver visibility, Python version, virtual environment creation, CUDA-enabled PyTorch installation, project dependencies, and CUDA verification.
- [x] 1.2 Document local asset transfer rules for `datasets/court-line-coco/`, regenerated `datasets/court-line-yolo/`, ignored `runs/`, and selected `models/court-line/best.pt`.
- [x] 1.3 Add copyable PowerShell examples for validating the dataset, preparing the YOLO segmentation dataset, and starting training with `cuda:0`.

## 2. PowerShell Helper Script

- [x] 2.1 Add a Windows PowerShell script under `scripts/` for court-line segmentation setup and training.
- [x] 2.2 Support configurable dataset root, converted output path, model, image size, epochs, batch, device, project output, run name, prepare-only mode, and optional PyTorch install command.
- [x] 2.3 Make the script create or reuse `backend/.venv`, upgrade pip, install CUDA-enabled PyTorch when requested, install backend requirements, and report dependency status.
- [x] 2.4 Make the script verify `torch.cuda.is_available()` before CUDA training and fail clearly when CUDA is unavailable unless CPU mode is explicitly selected.
- [x] 2.5 Make the script call the existing validation and training script with Windows-safe paths and arguments.

## 3. Verification

- [x] 3.1 Run OpenSpec validation/status checks for the change artifacts.
- [x] 3.2 Run a local syntax or parse check for the PowerShell script where available.
- [x] 3.3 Run the existing COCO validation or prepare-only path from the current environment to confirm the documented workflow still matches the Python scripts.
- [x] 3.4 Review the documentation for stale absolute paths, committed-large-asset risk, and unclear Windows command examples.
