# Local Model Weights

Place local YOLO11, RTMPose26, or future model checkpoints here during development.

Model weights are intentionally ignored by git because they are large, machine-specific, and may have separate license constraints.

## Pickleball Ball and Multi-target Models

Ball and future paddle detectors can live under dedicated subdirectories such as:

```text
models/pickleball-multitarget/
  model.pt
  classes.json
```

The active backend can enable ball analysis through:

```bash
PICKLEBALL_ENABLE_BALL_DETECTION=true
PICKLEBALL_BALL_MODEL_PATH=../models/pickleball-multitarget/model.pt
PICKLEBALL_ENABLE_BOUNCE_DETECTION=true
```

The pipeline keeps these switches off by default so local development and CI do
not require heavy model assets. When enabled without a valid model path or
runtime dependency, analysis jobs report a skipped or unavailable ball-analysis
stage instead of failing the player tracking, pose, serve, or movement outputs.

Detector adapters should normalize model output into `player` and `ball`
records today. `paddle` remains a supported direction for later adapters, but it
is not required for the current pipeline activation.

## RTMPose26 Validation Assets

The first supported skeleton model is OpenMMLab RTMPose Body8-Halpe26 with 26
keypoints. Put the config and checkpoint under:

```text
models/rtmpose/
  rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth
  configs/
    _base_/default_runtime.py
    _base_/datasets/halpe26.py
    body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py
```

Download sources:

- Config: https://github.com/open-mmlab/mmpose/tree/dev-1.x/configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py
- Checkpoint: https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth

Run the backend with:

```bash
PICKLEBALL_ENABLE_POSE_INFERENCE=true
PICKLEBALL_RTMPOSE_CONFIG_PATH=../models/rtmpose/configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py
PICKLEBALL_RTMPOSE_CHECKPOINT_PATH=../models/rtmpose/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth
PICKLEBALL_RTMPOSE_DEVICE=cpu
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
```

Use `PICKLEBALL_RTMPOSE_DEVICE=cuda:0` only after `torch.cuda.is_available()`
returns `True`.
