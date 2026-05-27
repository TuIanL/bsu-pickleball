## Context

当前系统已经具备固定机位匹克球视频的基础视觉分析能力：上传视频、球场标定、YOLO person 检测、IOU 多目标跟踪、主球员筛选、RTMPose 可选姿态、轨迹和指标输出。现有 `real_video_frame_extraction` 只面向球场线标注帧池，按时间间隔抽取原始帧，不做目标球员 crop，也不构造连续动作片段。

动作分类训练需要另一种数据产物：稳定目标球员在连续时间窗口内的裁剪图像。户外素材存在强光、树影、多人、远近差异、球拍小等问题，预处理必须先缩小场景范围，再稳定目标人物，最后导出可人工检查、可重复生成的训练样本。

## Goals / Non-Goals

**Goals:**

- 提供本地离线 CLI，把一个视频或视频目录导出为动作分类训练样本。
- 支持统一目标 FPS、固定比例 court ROI、CLAHE、可选轻微降噪、YOLO person 检测、目标球员选择、bbox 外扩、resize 和 clip 构造。
- 默认输出 JPEG 帧和 manifest，保留源视频、帧号、时间戳、ROI、检测框、目标选择策略、clip label 等调试信息。
- 复用现有 `PersonDetector` 和 `MultiObjectTracker`，避免复制 YOLO 集成逻辑。
- 让核心图像处理函数可单元测试，不依赖真实模型即可验证 ROI、CLAHE、bbox、clip 和 manifest 行为。

**Non-Goals:**

- 不训练 ResNet、LSTM 或视频动作识别模型。
- 不新增前端标注界面。
- 不改变现有视频分析 job flow、报告页面、轨迹指标或 overlay API。
- 不强制保存 `.npy` 或 PyTorch tensor；第一版以 JPEG/manifest 为主。
- 不把 ByteTrack、DeepSORT 或姿态特征作为第一版必需依赖。

## Decisions

### 独立离线预处理管线

新增 `backend/app/vision/action_classification_preprocessing/` 和 `backend/scripts/export_action_classification_dataset.py`，而不是把导出逻辑塞进 `AnalysisPipeline`。

理由：产品分析 job 关注一次上传后的报告产物，动作分类预处理关注批量训练数据构建、重复实验和人工质检，两者的生命周期、输出目录和参数都不同。独立管线可以复用视觉基础设施，同时避免影响现有 API。

备选方案：在现有分析 job 后追加训练样本 artifact。该方案短期看方便，但会把训练集构建参数暴露到用户分析流程，且容易让报告任务承担大量离线数据导出工作。

### 目标 FPS 抽样优先于 frame stride

预处理配置使用 `target_fps`，默认 20fps。运行时根据源视频 FPS 计算抽样间隔或目标时间序列，而不是复用 `PICKLEBALL_OVERLAY_FRAME_STRIDE`。

理由：动作分类模型需要跨不同手机视频的时间尺度一致；叠加层 frame stride 是为了可视化平滑度和推理成本服务，语义不同。

备选方案：继续使用 frame stride。该方案在 30/60/120fps 视频上会得到不同训练时间密度，不利于动作分类。

### ROI 在检测前执行，并保留坐标映射

第一版支持固定比例 court ROI，默认可从用户建议值开始：`x1=0.02, y1=0.30, x2=0.98, y2=0.98`。检测和 crop 可以在 ROI 图像上执行，但 manifest MUST 记录 ROI 偏移，并能保存 ROI 内 bbox 与源图 bbox。

理由：裁掉天空、树、篮球架和围栏能降低背景干扰；保留坐标映射方便调试、可视化和未来复用现有全帧跟踪数据。

备选方案：全帧检测后再裁 ROI。该方案对远端小人物更完整，但背景误检更多，且计算量更大。可以作为后续配置选项，不作为第一版默认。

### CLAHE 默认用于导出图像，检测输入可配置

第一版默认开启 CLAHE，参数 `clip_limit=2.0`、`tile_grid_size=8`。检测默认使用 ROI 原图，导出的 crop 使用增强后的 ROI；配置允许检测也使用 CLAHE。

理由：CLAHE 对树影和局部明暗差异有帮助，但 YOLO 模型通常在自然图像分布上训练，过度增强可能改变检测表现。把检测输入和导出图像解耦可以做 A/B 实验。

备选方案：检测和导出都强制 CLAHE。该方案简单，但误检风险更高。

### 目标选择先支持可重复的自动策略，并预留手动目标

第一版支持以下选择策略：

- `largest`: 选择面积最大的 person box，适合近端单主角素材。
- `near-left` / `near-right`: 按画面位置和面积偏好选择目标球员。
- `track-iou`: 根据上一帧目标 bbox 的 IoU 在当前检测结果中延续目标。
- `manual-initial-bbox`: 从配置传入初始 bbox，后续用 IoU 跟踪延续。

理由：数据建设初期需要稳定和可复现。手动框选 UI 可后续增加，第一版用配置传入 bbox 即可覆盖最稳场景。

备选方案：直接使用现有 `PrimaryPlayerSelector`。它更适合选择最多 4 个比赛主体用于 overlay，不完全等价于“训练标签对应的目标球员”。

### 输出 JPEG clip 和 manifest

默认目录结构为 `dataset_processed/<label>/<video_stem>_clipNNNN/frame_XXX.jpg`，同时写入根级 `manifest.json` 和每个 clip 的元数据。

理由：JPEG 便于快速人工检查预处理质量；manifest 支撑后续训练脚本读取、复现实验和排查漏检。

备选方案：直接输出 `.npy`。该方案训练读取更直接，但不利于初期发现裁剪错误、目标切换和光照增强问题。

### normalization 留给训练 dataloader

导出阶段保存 RGB 语义正确的图像文件和尺寸，不把 ImageNet normalization 固化到磁盘产物。

理由：normalization 是模型训练配置的一部分，ResNet50、视频模型或未来自训练 backbone 的均值方差可能不同。保存归一化后的图像也不便人工查看。

备选方案：导出 `.npy` 时直接保存 normalized tensor。该方案可作为未来加速选项。

## Risks / Trade-offs

- ROI 比例不适配所有机位 -> 将 ROI 写入配置和 manifest，允许按数据集调整，并在 manifest 中记录源尺寸与裁剪尺寸。
- YOLO 漏检远端球员 -> 检测阈值单独配置，默认建议 0.4 到 0.5；无检测帧可选择跳过、复用上一框或标记 clip 不完整。
- IoU 简单跟踪在遮挡或多人交叉时可能换人 -> manifest 记录目标选择来源和置信度，后续可替换 ByteTrack/BoT-SORT 而不改变输出契约。
- CLAHE 可能放大噪点或使画面过锐 -> 参数可配置，并保留关闭增强的实验路径。
- clip 边界可能切断动作 -> 第一版支持固定长度滑窗和 stride，后续可接入人工动作起止标注或发球开始检测。
- 批量 YOLO 导出耗时较长 -> CLI 支持视频级进度、最大 clip 数、时间范围和覆盖控制，先保证可重复，不在第一版引入复杂并行调度。

## Migration Plan

该变更是新增离线能力，不需要数据迁移。实现后可用小型 synthetic frame 测试核心函数，再用一段本地真实视频试跑 CLI，检查 manifest 和输出 crop。

如需回滚，只需不使用新增 CLI；现有分析 API 和前端不受影响。

## Open Questions

- 训练标签最初由目录名提供，还是需要单独的 CSV/JSON 标注文件描述动作起止时间？
- 第一批数据更偏向复现论文的 3 帧输入，还是直接以 16 帧作为默认训练 clip？
- 是否要在后续 proposal 中增加一个轻量人工质检页面，用于快速剔除换人、漏检和裁剪失败 clip？
