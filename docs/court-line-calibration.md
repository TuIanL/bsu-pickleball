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
  --epochs 100 \
  --batch -1
```

Thin painted lines are easy to lose at small input sizes, so start with
`--imgsz 960` or `--imgsz 1280`. Use source-aware train/val/test splits when
possible; splitting near-duplicate frames from one video across train and val
will make validation metrics look better than real deployment quality.

## Windows 11 NVIDIA Training

Use this path when a Windows 11 collaborator will train on an NVIDIA GPU. Keep
the clone in a short ASCII path such as `C:\work\pre-pickleball`; Windows tools
and some ML packages are less forgiving of synced folders or non-ASCII paths.

Machine prerequisites:

1. Install a current NVIDIA driver.
2. Open PowerShell and confirm the driver sees the GPU:

   ```powershell
   nvidia-smi
   ```

3. Install Python 3.11 and Git.
4. Clone the repository, then copy only the source COCO dataset into:

   ```text
   C:\work\pre-pickleball\datasets\court-line-coco\
     train\
       *.jpg
       _annotations.coco.json
     valid\
       *.jpg
       _annotations.coco.json
     test\
       *.jpg
       _annotations.coco.json
   ```

Do not copy `datasets/court-line-yolo/` from another machine unless you know the
generated YAML paths are valid for Windows. The conversion step is deterministic,
and regenerating it locally avoids stale macOS/Linux absolute paths.

Create the environment manually:

```powershell
cd C:\work\pre-pickleball\backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

Install CUDA-enabled PyTorch before the rest of the requirements. Use the
current selector at https://pytorch.org/get-started/locally/ and choose
Windows, Pip, Python, and the CUDA build that matches the machine. After
installing PyTorch, install the project dependencies:

```powershell
pip install -r requirements.txt
```

Confirm PyTorch can see CUDA before training:

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.version.cuda)"
```

The second line must be `True` for GPU training. If it is `False`, fix the
driver/PyTorch installation before running a long job.

Validate and prepare data:

```powershell
python scripts\validate_coco_segmentation.py --dataset-root ..\datasets\court-line-coco
python scripts\train_court_line_segmentation.py `
  --dataset-root ..\datasets\court-line-coco `
  --converted-output ..\datasets\court-line-yolo `
  --prepare-only
```

Start with a conservative CUDA training run:

```powershell
python scripts\train_court_line_segmentation.py `
  --dataset-root ..\datasets\court-line-coco `
  --converted-output ..\datasets\court-line-yolo `
  --model yolo11n-seg.pt `
  --imgsz 960 `
  --epochs 100 `
  --batch -1 `
  --device cuda:0 `
  --project ..\runs\court-line `
  --name court-line-seg
```

Use `--imgsz 1280` after the first run if the GPU has enough memory and the
thin court lines need more resolution.

### PowerShell Helper

The repository also includes a Windows helper script that wraps the same steps:

```powershell
cd C:\work\pre-pickleball
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
$TorchInstall = "python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128"
.\scripts\train-court-line-windows.ps1 `
  -TorchInstallCommand $TorchInstall `
  -PrepareOnly
```

The `cu128` command above is only an example. Use the current command from the
PyTorch selector if it recommends a different CUDA wheel for the Windows GPU.

Run the full training job after the prepare-only command succeeds:

```powershell
.\scripts\train-court-line-windows.ps1 `
  -Device cuda:0 `
  -ImgSize 960 `
  -Epochs 100 `
  -Batch "-1"
```

Useful options:

- `-DatasetRoot C:\data\court-line-coco` uses an external source dataset.
- `-ConvertedOutput C:\data\court-line-yolo` writes regenerated YOLO data outside the repo.
- `-Model yolo11s-seg.pt` tries a larger segmentation model.
- `-AllowCpu` permits CPU execution for debugging; omit it for real GPU training.
- `-SkipInstall` reuses an already prepared environment.

Local assets stay ignored by Git:

- Transfer `datasets/court-line-coco/` as a zip, external drive folder, or cloud
  share; this is the source dataset.
- Regenerate `datasets/court-line-yolo/` on the Windows machine.
- Keep training outputs under `runs/court-line/`.
- Copy the chosen trained checkpoint to `models/court-line/best.pt` when it
  should be used by the local runtime.

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
