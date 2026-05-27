## Why

现有后端已经能对上传视频做人检测、跟踪、主球员筛选和轨迹输出，但还缺少面向机器学习动作分类训练的离线预处理能力。匹克球素材存在户外强光、树影、多人、背景复杂、球拍和球很小等问题，需要先稳定导出目标球员连续帧 crop，才能支撑后续 forehand、backhand、serve 等动作分类模型训练。

## What Changes

- 新增动作分类预处理数据导出能力，将原始 `.MOV`/`.mp4` 视频处理为统一格式的训练 clip 样本。
- 支持按目标 FPS 抽帧，默认面向动作分类统一到 20fps，而不是复用现有叠加层 frame stride。
- 支持固定比例球场 ROI、CLAHE 光照增强、可选轻微降噪、YOLO person 检测、目标球员选择/跟踪、bbox 外扩、224x224 resize 和 clip 构造。
- 支持以 label 为目录组织输出，默认保存 JPEG 帧和 manifest，便于人工检查预处理质量。
- 复用现有 `PersonDetector`、`MultiObjectTracker` 和相关 schema 约定，同时把训练数据导出与现有产品分析 job flow 解耦。
- 新增 CLI 脚本用于本地批量导出训练样本，并提供可测试的核心处理函数。

## Capabilities

### New Capabilities
- `action-classification-preprocessing`: 面向动作分类训练的数据预处理与 clip 导出，包括抽帧、ROI、增强、目标球员 crop、连续帧样本组织和 manifest 记录。

### Modified Capabilities
- 无。

## Impact

- 影响后端视觉代码：新增 `backend/app/vision/action_classification_preprocessing/` 模块。
- 影响脚本入口：新增 `backend/scripts/export_action_classification_dataset.py`。
- 影响测试：新增动作分类预处理单元测试，覆盖 ROI、CLAHE、bbox 外扩、clip 分组、manifest 和无检测降级场景。
- 依赖层面复用现有 OpenCV、Ultralytics YOLO 和 pytest，不强制引入 PyTorch 训练依赖。
- 不改变现有上传分析 API、工作流编排、可视化叠加层和报告页面行为。
