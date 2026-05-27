## 1. 模块与配置

- [x] 1.1 新增 `backend/app/vision/action_classification_preprocessing/` 包和 `__init__.py`
- [x] 1.2 定义预处理配置 dataclass 或 Pydantic schema，覆盖输入、输出、label、target_fps、ROI、CLAHE、denoise、detector_confidence、selection_strategy、bbox_expand_scale、output_size、clip_length、clip_stride、overwrite 和时间范围
- [x] 1.3 定义 manifest 数据结构，包含数据集汇总、视频汇总、clip 记录、帧记录、ROI、bbox、目标选择和错误诊断字段
- [x] 1.4 增加配置校验，拒绝非法 FPS、ROI 比例、clip 长度、输出尺寸、bbox 外扩比例和未知目标选择策略

## 2. 核心图像处理

- [x] 2.1 实现视频发现和唯一 output stem 生成，复用或对齐现有 `discover_video_paths` 与 `sanitize_video_stem` 行为
- [x] 2.2 实现按 `target_fps` 和可选时间范围生成待处理源帧号与时间戳
- [x] 2.3 实现 court ROI 裁剪，并返回 ROI 图像、比例坐标、像素坐标和源图坐标映射偏移
- [x] 2.4 实现 CLAHE BGR 增强函数，支持 `clip_limit` 和 `tile_grid_size`
- [x] 2.5 实现可选轻微 GaussianBlur 降噪，默认关闭
- [x] 2.6 实现 bbox 外扩、边界 clamp、目标 crop 和固定尺寸 resize

## 3. 检测、目标选择与帧样本

- [x] 3.1 复用现有 `PersonDetector`，允许注入 fake detector 以便测试
- [x] 3.2 实现 `largest`、`near-left`、`near-right` 目标选择策略
- [x] 3.3 实现 `manual-initial-bbox` 和 `track-iou` 延续策略，基于上一目标 bbox 选择 IoU 最高检测
- [x] 3.4 实现无检测帧处理策略，至少支持跳过并记录原因
- [x] 3.5 为每个成功帧生成帧级记录，包含源帧号、时间戳、ROI bbox、源图 bbox、crop bbox、confidence 和输出路径

## 4. Clip 构造与导出

- [x] 4.1 实现从连续成功帧按 `clip_length` 和 `clip_stride` 构造 clip
- [x] 4.2 按 `output_root/<label>/<video_stem>_clipNNNN/` 写入 JPEG 帧
- [x] 4.3 实现 overwrite 保护，默认拒绝覆盖已有 clip 或 manifest
- [x] 4.4 生成根级 `manifest.json`，汇总视频、clip、帧、错误和最终配置
- [x] 4.5 在没有完整 clip 时返回非成功摘要，并在 manifest 或 CLI 输出中说明原因

## 5. CLI 脚本

- [x] 5.1 新增 `backend/scripts/export_action_classification_dataset.py`
- [x] 5.2 支持单视频和目录输入、输出目录、label、target FPS、ROI、CLAHE、检测阈值、目标选择、clip 长度、clip stride、时间范围和 overwrite 参数
- [x] 5.3 CLI 输出 JSON 摘要，包含处理视频数、生成 clip 数、写入帧数、跳过帧数和错误数
- [x] 5.4 在 `backend/README.md` 或相关 docs 中补充最小运行示例和推荐参数

## 6. 测试与验证

- [x] 6.1 新增 ROI、CLAHE、bbox 外扩和 resize 的单元测试
- [x] 6.2 新增目标选择策略测试，覆盖多人 bbox、near-left、near-right、largest 和 IoU 延续
- [x] 6.3 新增 clip 构造和 manifest 测试，覆盖完整 clip、不足 clip、滑窗步长和路径结构
- [x] 6.4 新增 fake detector 驱动的端到端导出测试，使用合成视频或 mock frame reader 验证无真实 YOLO 时的可测试性
- [x] 6.5 运行后端 pytest，确保新增能力不破坏现有分析 pipeline 测试
