## Context

项目已具备完整的人体检测（YOLO11）、姿态估计（RTMPose Halpe26）和骨架绘制能力，但这些能力分散在 `AnalysisPipeline`、`RTMPose26Adapter`、`export_pose_overlay_video.py` 等模块中，缺乏一条为"快速演示"场景优化的捷径。当前任何姿势叠加视频的生成都需要：上传视频 → 创建分析任务 → 等待 pipeline 完成 → 手动运行 `export_pose_overlay_video.py`。对于论文中只需处理几秒挥拍片段、拿到骨架图和逐帧照片的场景，这个流程过于沉重。

## Goals / Non-Goals

**Goals:**
- 提供一条 CLI 即可运行的捷径：`python backend/scripts/export_swing_skeleton.py --video <路径>`
- 对多人本方挥拍场景做检测 + 轻量跟踪 + 姿态估计 + 骨架叠加
- 同步输出：带骨架的 `overlay.mp4` + `frames/` 逐帧 JPG 照片集
- 按视频名称组织输出目录结构

**Non-Goals:**
- 不做球场标定、脚点投影、发球检测等完整 pipeline 功能
- 不做 Web API 接口，纯 CLI
- 不修改现有 pipeline 或模块的 API
- 不支持前端实时预览

## Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| 复用 vs 重写绘制逻辑 | 直接 import `export_pose_overlay_video.py` 中的 `draw_pose_frame` 等函数 | 绘制逻辑已稳定，避免代码重复；这些函数是纯函数，无副作用 |
| 跟踪策略 | IoU 交并比关联（简陋但有效） | 短挥拍视频中本方球员不会交叉换位，IoU 足以维持 ID 稳定；无需引入 DeepSORT |
| 帧步长 | stride=1（每帧处理） | 演示场景需要完整逐帧照片集，跳帧会产生缺失 |
| 单人/多人 | 检测所有 person，对每人做姿态估计 | 本方半场可能有 1-2 名球员，都需要展示骨架 |
| 输出格式 | JPG（quality=95） | 论文配图常用格式，文件大小可控 |
| 视频编码 | H.264（`avc1` fourcc） | 兼容性好，论文展示/PPT 嵌入无问题 |
| 模型加载 | 懒加载（首次推理时才加载） | 与项目现有模式一致，避免无关场景的内存占用 |

## Risks / Trade-offs

- **MMPose 依赖较重**（mmcv-full、mmengine、torch）→ 脚本启动时做依赖检查，清晰报错
- **IoU 跟踪在极端情况下会 ID 跳变**（两人短暂重叠后分离）→ 短挥拍场景几乎不会发生；若发生，论文中使用帧挑选即可规避
- **GPU 内存**（同时加载 YOLO + RTMPose）→ 默认使用 CPU 推理，通过 `--device` 参数可选 GPU

## Open Questions

无待解决事项。所有技术选型在探索阶段已确认。
