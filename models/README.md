# Local Model Weights

Place local YOLO11, RTMPose26, or future model checkpoints here during development.

Model weights are intentionally ignored by git because they are large, machine-specific, and may have separate license constraints.

## RTMPose26 Validation Assets

The first supported skeleton model is OpenMMLab RTMPose Body8-Halpe26 with 26
keypoints. Put the config and checkpoint under:

```text
models/rtmpose/
  rtmpose-m_8xb512-700e_body8-halpe26-256x192.py
  rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth
```

Download sources:

- Config: https://github.com/open-mmlab/mmpose/tree/dev-1.x/configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py
- Checkpoint: https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth

Run the backend with:

```bash
PICKLEBALL_ENABLE_POSE_INFERENCE=true
PICKLEBALL_RTMPOSE_CONFIG_PATH=../models/rtmpose/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py
PICKLEBALL_RTMPOSE_CHECKPOINT_PATH=../models/rtmpose/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth
PICKLEBALL_RTMPOSE_DEVICE=cpu
```

Use `PICKLEBALL_RTMPOSE_DEVICE=cuda:0` only after `torch.cuda.is_available()`
returns `True`.
