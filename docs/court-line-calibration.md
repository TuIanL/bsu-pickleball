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

## Real Video Frame Pool

When most available images come from online match footage, first build a local
frame pool from real videos captured on the target courts. These frames are
pending annotation assets, not a train-ready COCO dataset.

Use a local ignored folder for source videos, for example:

```text
datasets/real-court-videos/
  phone-court-01.mp4
  tripod-court-02.mov
```

Extract annotation candidates into an ignored frame pool:

```bash
cd backend
python3 scripts/extract_real_video_frames.py \
  ../datasets/real-court-videos \
  --output-root ../datasets/real-court-frame-pool \
  --interval-seconds 2.0 \
  --max-frames-per-video 200
```

The extractor accepts either one video file or a directory of supported videos.
Useful controls:

- `--interval-seconds 1.0` samples more densely when rallies are short.
- `--max-frames-per-video 100` keeps one long recording from dominating the
  frame pool.
- `--start-seconds 30 --end-seconds 180` skips setup, warmup, or irrelevant
  footage.
- `--jpeg-quality 95` controls output image quality.
- `--overwrite` replaces previously extracted frames with the same generated
  names.

Outputs are grouped by source video and include `manifest.json`:

```text
datasets/real-court-frame-pool/
  manifest.json
  phone-court-01/
    phone-court-01_f000000_t00000.00s.jpg
    phone-court-01_f000060_t00002.00s.jpg
```

Each frame filename includes the source video stem, source frame index, and
timestamp. The manifest records source paths, output paths, FPS, frame
dimensions, sampling settings, and any per-video errors. Keep this manifest when
uploading frames to an annotation tool so source-video grouping can be reviewed
later.

For the first real-scene adaptation pass, manually label the visible pickleball
court region as `Court`. This matches the currently used local dataset more
closely than strict thin-line `Court-Line` annotation and is faster to label for
phone or tripod footage. After annotation, export COCO segmentation and place it
under a normal dataset root such as:

```text
datasets/court-line-coco-real/
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

Split by source video, not by random frame. Reserve at least one real captured
video for validation or test before fine-tuning, and do not place frames from
that same source video into train. This prevents near-duplicate frames from
making validation results look better than real deployment quality.

## Validate COCO Segmentation

```bash
cd backend
python3 scripts/validate_coco_segmentation.py \
  --dataset-root ../datasets/court-line-coco
```

The validator checks image references, category IDs, polygon/RLE segmentation
records, missing files, category usage, unused categories, split leakage risk,
and train/validation/test readiness. Use it before training so broken annotation
paths and ambiguous target labels are caught early.

The report separates two readiness layers:

- `structural_ready`: the COCO files, images, annotations, and required splits
  are readable.
- `target_ready`: the observed annotations match the declared model target.

For a strict category target:

```bash
cd backend
python3 scripts/validate_coco_segmentation.py \
  --dataset-root ../datasets/court-line-coco-real \
  --target-category Court
```

For one-class MVP training that intentionally merges all annotated categories
into a single mask:

```bash
cd backend
python3 scripts/validate_coco_segmentation.py \
  --dataset-root ../datasets/court-line-coco \
  --target-strategy merge
```

If a category such as `Court-Line` exists in the COCO category list but has zero
annotations, the report marks that category as unused instead of silently
treating it as the training target. This is important when deciding whether the
first model should learn court lines, the whole court region, or a merged
single-class mask.

### Dataset Acceptance Evidence

Write project-review evidence to an ignored local folder:

```bash
cd backend
python3 scripts/validate_coco_segmentation.py \
  --dataset-root ../datasets/court-line-coco \
  --target-strategy merge \
  --evidence-output ../datasets/court-line-coco/acceptance \
  --preview-samples-per-split 3
```

The evidence folder contains:

- `summary.json`: structural readiness, target readiness, split/category
  statistics, unused categories, warnings, and split-leakage examples.
- `previews/`: representative annotation overlays for train, validation, and
  test samples when OpenCV can read the source images.

Split leakage warnings are diagnostic, not automatic failures. They usually mean
that normalized image names or source metadata suggest related frames appear in
multiple splits. Review those examples before treating validation or test
metrics as final acceptance numbers.

## Prepare and Train

For a dry run that validates the dataset and writes a YOLO segmentation dataset:

```bash
cd backend
python3 scripts/train_court_line_segmentation.py \
  --dataset-root ../datasets/court-line-coco \
  --converted-output ../datasets/court-line-yolo \
  --prepare-only
```

For real-scene `Court` annotations exported from the frame pool, point
`--dataset-root` at that export, such as `../datasets/court-line-coco-real`, or
at a source-aware merged dataset that keeps held-out real videos out of train.

To train with Ultralytics:

```bash
cd backend
python3 scripts/train_court_line_segmentation.py \
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
