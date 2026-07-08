## Why

论文中需要展示姿态估计算法的处理效果，目前项目缺少一个轻量的"视频进、骨架图出"的独立工具。现有的分析 pipeline 绑定了完整的上传→任务→分析流程，对于只需快速生成骨架叠加视频 + 逐帧照片集的演示场景过于笨重。

## What Changes

- 新增独立 CLI 脚本 `backend/scripts/export_swing_skeleton.py`，跳过 job/pipeline 体系，直接读取视频文件
- 复用现有的 `PersonDetector`（YOLO 人体检测）+ `RTMPose26Adapter`（26 点姿态估计）+ IoU 轻量跟踪
- 复用 `export_pose_overlay_video.py` 中的骨架绘制函数（`draw_skeleton`、`draw_keypoints`、`draw_bbox`、`draw_label`），直接绘制到原始帧上
- 同步输出两个产物：带骨架的叠加视频（`overlay.mp4`）+ 逐帧 JPG 照片集（`frames/` 目录）
- 每段输入视频在 `outputs/<视频名>/` 下生成独立文件夹

## Capabilities

### New Capabilities
- `swing-skeleton-export`: 轻量级挥拍视频骨架叠加导出工具，输入视频直接输出骨架叠加视频和逐帧照片集

### Modified Capabilities
<!-- 本次变更不修改任何已有能力的 spec 级需求，仅新增独立脚本 -->

## Impact

- **新增文件**: `backend/scripts/export_swing_skeleton.py`
- **复用模块**: `backend/app/vision/pose/rtmpose26_adapter.py`、`backend/app/vision/player_tracking_engine/person_detector.py`、`backend/scripts/export_pose_overlay_video.py`（绘制函数）
- **依赖**: ultralytics、mmpose、mmcv、mmengine、torch、opencv-python、numpy
- **输出目录**: `outputs/<video_stem>/`（每个视频独立文件夹）
