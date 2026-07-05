## ADDED Requirements

### Requirement: Court-view gated player tracking
Player Tracking Engine SHALL 支持 court-view gate 对真实视频帧的检测、跟踪和姿态输入进行保守门控，同时保留与普通无检测帧不同的诊断。

#### Scenario: 非球场视角帧跳过检测
- **WHEN** court-view gate 明确判定当前处理帧不是目标球场视角且门控跳过已启用
- **THEN** Player Tracking Engine SHALL 跳过该帧的 person detection 和 pose estimation，并记录 gated frame 诊断

#### Scenario: Court-view gate 不可用
- **WHEN** court-view gate 状态为 `unavailable`、`skipped` 或诊断-only
- **THEN** Player Tracking Engine SHALL 使用现有检测、跟踪、投影路径继续处理可用帧

#### Scenario: Gated frame 不伪装成无检测
- **WHEN** 一帧因 court-view gate 被跳过
- **THEN** tracking diagnostics SHALL 区分 `gated_non_court_view` 与模型运行后 `no_detections`，以便任务详情和测试能解释轨迹缺口

### Requirement: ROI-aware person detection
Player Tracking Engine SHALL 在 detection ROI 可用时限制 person detection 输入或过滤 detection 输出，以减少目标球场外人物干扰。

#### Scenario: ROI 裁剪检测输入
- **WHEN** detection ROI 可用且实现选择在 ROI 上运行模型
- **THEN** detector SHALL 将 ROI 内检测框转换回源帧坐标后再交给 tracker、projector、pose estimator 和 overlay artifact

#### Scenario: ROI 过滤检测输出
- **WHEN** detection ROI 可用且实现选择全帧推理后过滤
- **THEN** Player Tracking Engine SHALL 排除 ROI 外 person detections 进入 match-relevant tracking 路径，并记录过滤数量

#### Scenario: ROI 不可用时全帧回退
- **WHEN** detection ROI 不可用或被配置禁用
- **THEN** Player Tracking Engine SHALL 回退到现有全帧检测行为，并在诊断中记录 full-frame fallback

### Requirement: ROI 与投影坐标一致
ROI-aware detection SHALL preserve source-frame coordinate semantics for tracking, projection, pose overlay, and frontend rendering.

#### Scenario: 投影使用源帧脚点
- **WHEN** ROI-aware detection 产生 player bbox 并估计 footpoint
- **THEN** footpoint projection SHALL 使用源视频坐标系下的 footpoint，而不是 ROI-local 坐标

#### Scenario: Pose overlay 使用源帧尺寸
- **WHEN** pose estimator 消费 ROI-aware detection subjects
- **THEN** pose overlay artifact SHALL 继续声明源视频 frame width/height，并输出可与 source video 对齐的 keypoints

#### Scenario: ROI 过滤不删除原始诊断
- **WHEN** ROI 过滤排除了检测框
- **THEN** 系统 SHALL 在 tracking 或 court-view/ROI artifact 中保留被过滤计数和原因，以便调试邻场或观众误检
