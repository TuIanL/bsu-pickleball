## ADDED Requirements

### Requirement: CLI 入口接收视频路径

脚本 SHALL 通过 `--video` 参数接收一个或多个视频文件路径，支持 `.mp4`、`.mov`、`.avi`、`.mkv`、`.webm` 格式。

#### Scenario: 单个视频输入

- **WHEN** 用户执行 `python backend/scripts/export_swing_skeleton.py --video swing.mp4`
- **THEN** 脚本加载该视频并开始逐帧处理

#### Scenario: 不支持的格式

- **WHEN** 用户指定一个非视频格式文件（如 `.jpg`）
- **THEN** 脚本输出明确的错误信息并退出

### Requirement: YOLO 人体检测

脚本 SHALL 使用 `PersonDetector`（基于 YOLO11）对每一帧进行人体检测，返回所有检测到的 person 边界框。

#### Scenario: 单帧多人检测

- **WHEN** 一帧画面中包含 2 名球员
- **THEN** 检测器返回 2 个 person 边界框，每个包含 `[x1, y1, x2, y2]` 和置信度

#### Scenario: 无人体帧

- **WHEN** 一帧画面中无人（如遮挡或空场）
- **THEN** 该帧仍写入视频和图片，但不绘制任何骨架叠加

### Requirement: IoU 轻量多人跟踪

脚本 SHALL 使用 IoU 交并比算法在相邻帧间关联检测结果，为每个球员分配稳定的整数 track_id。

#### Scenario: 跟踪 ID 稳定

- **WHEN** 同一球员在连续帧中移动
- **THEN** 该球员保持相同的 track_id，骨架颜色不变

#### Scenario: 球员进出画面

- **WHEN** 新球员首次进入检测区域
- **THEN** 系统为其分配新的 track_id

### Requirement: RTMPose 姿态估计

脚本 SHALL 对每个检测到的 person 调用 `RTMPose26Adapter`，获取 26 个 Halpe 关键点坐标及置信度。

#### Scenario: 成功估计姿态

- **WHEN** 检测框内人体清晰可见
- **THEN** 返回 26 个关键点坐标，每个包含 name、x、y、confidence、visible

#### Scenario: 姿态估计失败

- **WHEN** 检测框内图像质量不足以估计姿态
- **THEN** 该检测对象被跳过，不影响其他对象的处理

### Requirement: 骨架叠加绘制

脚本 SHALL 对每一帧在原始画面上叠加绘制：骨架连线（27 条边）、关键点圆点、球员 ID 标签、人物边界框。

#### Scenario: 多人骨架绘制

- **WHEN** 一帧中有 2 名球员各有有效关键点
- **THEN** 画面中显示 2 套不同颜色的完整骨架，每套包含连线、圆点、标签、边界框

### Requirement: 叠加视频输出

脚本 SHALL 将所有处理后的帧合成为 H.264 编码的 `.mp4` 视频文件，保存到 `outputs/<video_stem>/overlay.mp4`。

#### Scenario: 完整视频输出

- **WHEN** 处理完所有帧后
- **THEN** `outputs/<video_stem>/overlay.mp4` 存在且可正常播放，帧数与源视频一致

### Requirement: 逐帧照片集输出

脚本 SHALL 将每一帧（含骨架叠加）保存为独立的 JPG 图片，保存到 `outputs/<video_stem>/frames/frame_0001.jpg` 等路径，编号从 1 开始、4 位数字补齐。

#### Scenario: 照片集完整性

- **WHEN** 视频共 90 帧
- **THEN** `outputs/<video_stem>/frames/` 目录下存在 `frame_0001.jpg` 到 `frame_0090.jpg`，共 90 张图片

### Requirement: 依赖检查与报错

脚本 SHALL 在启动时检查必要的模型文件和 Python 依赖是否可用，缺失时输出可操作的错误信息。

#### Scenario: MMPose 未安装

- **WHEN** 运行环境中未安装 mmpose
- **THEN** 脚本输出 "mmpose 未安装，请运行 pip install mmpose mmcv mmengine" 并退出

#### Scenario: 模型文件缺失

- **WHEN** `models/rtmpose/` 下缺少配置文件或 checkpoint
- **THEN** 脚本输出明确的路径信息并退出

### Requirement: 命令行参数

脚本 SHALL 支持以下 CLI 参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--video` | Path（必填） | — | 输入视频路径 |
| `--output-dir` | Path | `outputs/` | 输出根目录 |
| `--device` | str | `cpu` | 推理设备（cpu/cuda/mps） |
| `--conf-threshold` | float | `0.25` | YOLO 检测置信度阈值 |
| `--keypoint-confidence` | float | `0.25` | 关键点绘制最低置信度 |
| `--no-boxes` | flag | False | 不绘制边界框 |
| `--no-labels` | flag | False | 不绘制 ID 标签 |

#### Scenario: 使用默认参数

- **WHEN** 用户仅指定 `--video`
- **THEN** 其他参数使用默认值运行
