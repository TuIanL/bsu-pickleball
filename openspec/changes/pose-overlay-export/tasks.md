## 1. 脚本骨架搭建

- [x] 1.1 创建 `backend/scripts/export_swing_skeleton.py`，添加 argparse CLI 参数（`--video`、`--output-dir`、`--device`、`--conf-threshold`、`--keypoint-confidence`、`--no-boxes`、`--no-labels`）
- [x] 1.2 实现启动依赖检查：验证 ultralytics、mmpose、mmcv、torch、cv2 可导入，缺失时给出清晰报错

## 2. 多人检测与跟踪

- [x] 2.1 集成 `PersonDetector`：加载 YOLO11 模型，对每一帧检测所有 person 边界框
- [x] 2.2 实现轻量 IoU 跟踪：在相邻帧间用交并比关联检测结果，维护稳定 track_id 和颜色映射

## 3. 姿态估计

- [x] 3.1 集成 `RTMPose26Adapter`：对每个跟踪到的 person 调用 `estimate_frame()`，获取 26 个 Halpe 关键点
- [x] 3.2 处理边界情况：检测框无效、姿态估计失败时优雅跳过

## 4. 骨架叠加绘制

- [x] 4.1 复用 `export_pose_overlay_video.py` 中的 `draw_pose_frame`、`draw_skeleton`、`draw_keypoints`、`draw_bbox`、`draw_label`、`color_for_track`
- [x] 4.2 将检测/跟踪/姿态结果转换为 `draw_pose_frame` 所需的 overlay 数据格式

## 5. 输出生成

- [x] 5.1 实现 H.264 视频编码输出：用 `cv2.VideoWriter` 将叠加后的帧合成为 `outputs/<video_stem>/overlay.mp4`
- [x] 5.2 实现逐帧 JPG 照片集输出：用 `cv2.imwrite` 将每帧保存为 `outputs/<video_stem>/frames/frame_0001.jpg` ~ `frame_NNNN.jpg`
- [x] 5.3 确保输出目录自动创建，同名输出覆盖

## 6. 端到端验证

- [ ] 6.1 用项目中的测试视频或示例帧跑通完整流程，确认 overlay.mp4 可播放且骨架正确（需安装 mmpose 运行时依赖）
- [ ] 6.2 确认 frames/ 目录下照片数量与视频帧数一致（需安装 mmpose 运行时依赖）
