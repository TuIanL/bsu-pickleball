## ADDED Requirements

### Requirement: 动作分类预处理配置
系统 SHALL 提供动作分类预处理配置，用于控制输入视频、输出目录、动作标签、目标 FPS、ROI、光照增强、检测阈值、目标选择、bbox 外扩、输出尺寸、clip 长度和滑窗步长。

#### Scenario: 使用默认预处理配置
- **WHEN** 用户运行动作分类预处理且未覆盖可选参数
- **THEN** 系统使用 20fps、224x224 输出尺寸、CLAHE 开启、bbox 外扩比例 1.4、JPEG 输出、固定长度 clip 和 manifest 记录

#### Scenario: 用户覆盖预处理参数
- **WHEN** 用户通过 CLI 参数或配置文件提供 ROI、目标 FPS、clip 长度、检测阈值或目标选择策略
- **THEN** 系统使用用户提供的参数处理视频，并在 manifest 中记录最终生效的配置

#### Scenario: 配置参数无效
- **WHEN** 用户提供非正数 FPS、非法 ROI 比例、非正数 clip 长度或无效输出尺寸
- **THEN** 系统拒绝开始导出并返回清晰的配置错误

### Requirement: 统一视频抽帧
系统 SHALL 按目标 FPS 从 `.MOV`、`.mp4` 或其他已支持视频格式中抽取训练帧，并保留源帧号和时间戳。

#### Scenario: 从高帧率视频抽样
- **WHEN** 源视频为 60fps 或 120fps 且目标 FPS 为 20fps
- **THEN** 系统按接近 20fps 的时间间隔处理帧，并在 manifest 中记录源 FPS、目标 FPS、源帧号和时间戳

#### Scenario: 视频无法解码
- **WHEN** OpenCV 无法打开输入视频或无法读取有效 FPS
- **THEN** 系统不生成误导性的训练样本，并在导出结果中记录视频级错误

#### Scenario: 限制处理时间范围
- **WHEN** 用户指定开始时间或结束时间
- **THEN** 系统只在指定时间范围内抽帧和构造 clip

### Requirement: 球场 ROI 和光照增强
系统 SHALL 能够在检测和导出前应用固定比例球场 ROI，并能对导出的图像应用 CLAHE 光照增强。

#### Scenario: 应用固定比例 ROI
- **WHEN** 配置包含 `x1_ratio`、`y1_ratio`、`x2_ratio` 和 `y2_ratio`
- **THEN** 系统按源帧尺寸裁剪 ROI，并在 manifest 中记录 ROI 像素坐标和比例坐标

#### Scenario: ROI 后保留源图坐标映射
- **WHEN** 系统在 ROI 图像中检测到目标球员 bbox
- **THEN** manifest 同时记录 ROI 内 bbox 和映射回源帧的 bbox

#### Scenario: 应用 CLAHE
- **WHEN** CLAHE 配置开启
- **THEN** 系统使用 LAB 亮度通道增强导出的 crop，并保留原始色彩通道关系

#### Scenario: 关闭 CLAHE
- **WHEN** CLAHE 配置关闭
- **THEN** 系统直接从未增强帧生成 crop，且 manifest 记录增强未启用

### Requirement: 人体检测与目标球员选择
系统 SHALL 复用现有 YOLO-backed person detector 识别人体框，并根据配置选择单个目标球员用于动作分类 crop。

#### Scenario: YOLO 检测多人
- **WHEN** 一帧 ROI 中检测到多个人体框
- **THEN** 系统根据配置的目标选择策略选择一个目标 bbox，并记录候选数量、目标 bbox、置信度和选择策略

#### Scenario: 使用位置策略选择目标
- **WHEN** 目标选择策略为 `largest`、`near-left` 或 `near-right`
- **THEN** 系统按 bbox 面积和画面位置规则选择目标球员

#### Scenario: 使用初始 bbox 跟踪目标
- **WHEN** 用户提供 `manual-initial-bbox`
- **THEN** 系统将初始 bbox 作为目标身份起点，并在后续帧中优先选择与上一目标 bbox IoU 最高的检测

#### Scenario: 当前帧无可用人体检测
- **WHEN** 当前帧没有通过阈值的人体框
- **THEN** 系统按配置跳过该帧、复用短期上一 bbox 或标记该帧不可用，且不得静默生成无来源的目标 crop

### Requirement: 目标球员 crop 导出
系统 SHALL 对目标球员 bbox 进行可配置外扩、边界裁剪和 resize，并输出动作分类模型可读取的图像帧。

#### Scenario: bbox 外扩并裁剪到边界内
- **WHEN** 目标 bbox 靠近图像边缘或外扩后超出 ROI 边界
- **THEN** 系统将外扩 bbox clamp 到有效图像范围内，并记录最终 crop bbox

#### Scenario: 输出固定尺寸图像
- **WHEN** 系统生成目标球员 crop
- **THEN** 输出图像尺寸为配置指定值，默认 224x224

#### Scenario: 保留球拍动作范围
- **WHEN** bbox 外扩比例配置为 1.3 到 1.5
- **THEN** 系统以 bbox 中心为基准扩展裁剪区域，以尽量保留手臂和球拍动作

### Requirement: 连续帧 clip 构造
系统 SHALL 将连续目标球员 crop 构造成固定长度训练 clip，并按动作标签组织输出目录。

#### Scenario: 构造固定长度 clip
- **WHEN** 连续可用 crop 数量达到配置的 `clip_length`
- **THEN** 系统生成一个 clip 目录，包含按顺序命名的帧图像和对应 manifest 记录

#### Scenario: 使用滑窗步长
- **WHEN** 用户配置 `clip_stride`
- **THEN** 系统按该步长从连续 crop 序列中生成后续 clip

#### Scenario: 按标签组织输出
- **WHEN** 用户为输入视频提供动作标签
- **THEN** 系统将 clip 保存到 `output_root/<label>/<video_stem>_clipNNNN/`

#### Scenario: 连续帧不足
- **WHEN** 某段可用 crop 数量不足以构成完整 clip
- **THEN** 系统不生成不完整训练 clip，并在 manifest 汇总中记录跳过数量

### Requirement: Manifest 和质量诊断
系统 SHALL 为导出的数据集生成 JSON manifest，描述输入视频、配置、输出 clip、帧级检测、目标选择、crop 参数和错误诊断。

#### Scenario: 导出成功
- **WHEN** 系统成功生成一个或多个训练 clip
- **THEN** 根级 manifest 包含视频列表、clip 列表、每个 clip 的 label、帧路径、源帧号、时间戳、ROI、bbox、置信度和预处理配置

#### Scenario: 部分帧失败
- **WHEN** 某些帧无法检测目标或无法写入图像
- **THEN** manifest 记录帧级错误和汇总计数，同时保留其他成功 clip

#### Scenario: 无训练样本生成
- **WHEN** 输入视频处理完成但没有生成任何完整 clip
- **THEN** 系统返回非成功状态或错误摘要，说明没有生成训练样本的原因

### Requirement: CLI 批量导出入口
系统 SHALL 提供本地 CLI，用于从单个视频或视频目录批量导出动作分类训练数据。

#### Scenario: 导出单个已标注视频
- **WHEN** 用户运行 CLI 并提供输入视频、输出目录和 label
- **THEN** 系统处理该视频并在输出目录下生成 label 分类的 clip 数据和 manifest

#### Scenario: 导出目录内多个视频
- **WHEN** 用户运行 CLI 并提供输入目录
- **THEN** 系统发现支持的视频文件并逐个处理，保证每个视频的输出 stem 唯一

#### Scenario: 输出已存在且未允许覆盖
- **WHEN** 目标 clip 或 manifest 已存在且用户未指定 overwrite
- **THEN** 系统拒绝覆盖已有训练数据，并返回需要用户确认的错误
