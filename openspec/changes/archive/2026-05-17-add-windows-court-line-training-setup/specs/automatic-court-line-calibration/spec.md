## ADDED Requirements

### Requirement: Windows CUDA training setup
The system SHALL document and support a Windows 11 + NVIDIA setup path for local court-line segmentation training without requiring datasets, generated YOLO data, training runs, or model weights to be committed to version control.

#### Scenario: Collaborator prepares Windows training environment
- **WHEN** a Windows 11 collaborator clones the repository for court-line segmentation training
- **THEN** the documentation provides Windows PowerShell commands for creating the backend Python environment, installing CUDA-enabled PyTorch and project training dependencies, verifying CUDA visibility, and validating the local dataset before training

#### Scenario: Collaborator transfers ignored dataset assets
- **WHEN** the source COCO court-line dataset is copied from another machine
- **THEN** the documentation identifies the required local `datasets/court-line-coco/` layout and explains that generated `datasets/court-line-yolo/` files should be regenerated on the Windows machine

### Requirement: Windows court-line training helper
The system SHALL provide a PowerShell helper that runs the Windows court-line segmentation setup and training workflow with explicit CUDA verification.

#### Scenario: Helper prepares and validates dataset
- **WHEN** the collaborator runs the helper with a valid dataset path and prepare-only mode
- **THEN** the helper creates or reuses the backend virtual environment, installs required dependencies, checks PyTorch CUDA availability unless CPU mode is explicitly selected, validates the COCO dataset, and prepares the YOLO segmentation dataset

#### Scenario: Helper starts GPU training
- **WHEN** the collaborator runs the helper with training enabled and `cuda:0` selected
- **THEN** the helper invokes the existing court-line training script with the configured dataset path, converted dataset path, model, image size, epoch count, batch setting, project output path, run name, and CUDA device

#### Scenario: CUDA is unavailable
- **WHEN** the helper is configured for CUDA training but PyTorch reports that CUDA is unavailable
- **THEN** the helper fails before starting model training and prints a clear diagnostic that points to PyTorch/CUDA installation or NVIDIA driver setup
