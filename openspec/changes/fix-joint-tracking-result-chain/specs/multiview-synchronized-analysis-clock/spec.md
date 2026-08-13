## ADDED Requirements

### Requirement: 分析帧解帧使用帧号语义

joint 执行体（`JointViewRuntime`）解析源帧 SHALL 使用帧号语义（`cv2.CAP_PROP_POS_FRAMES`）定位视频位置，MUST NOT 把帧号当作毫秒（`CAP_PROP_POS_MSEC`）消费。每次解帧的帧位置 SHALL 精确对应 bundle 给出的 `source_frame_index`，保证检测/跟踪运行在正确的源帧上。

#### Scenario: 解帧位置与帧号一致

- **WHEN** runtime 收到 `source_frame_index=400`
- **THEN** 解出的帧 SHALL 为视频第 400 帧（帧号语义）
- **AND** SHALL NOT 落在第 25 帧（400ms 位置）等错误位置

#### Scenario: 逐 tick 帧号严格前进

- **WHEN** 相邻 tick 的 `source_frame_index` 相差 2
- **THEN** 实际解出的帧 SHALL 逐 tick 前进 2 帧
- **AND** 检测框 SHALL 随每个 tick 更新，不得每 ~5-8 tick 才变化一次

### Requirement: 窗口开头副摄帧选择回退

当分析窗口起点（如 `clipStart=0`）早于 sync 有效映射起点（`valid_start_seconds`）时，clock SHALL 为 secondary view 提供显式回退策略：使用最近有效映射外推或最近可用帧，或保持细分不可用状态并携带结构化解释。任何回退 SHALL 在 `FrameSample` 上标注 fallback status 与 reason，MUST NOT 伪装为正常映射。

#### Scenario: 窗口开头副摄有回退帧

- **WHEN** canonical tick 时间戳早于 cam_2 的 `valid_start_seconds`（实测 3.4s）
- **THEN** cam_2 SHALL 使用回退帧选择并标记 `fallback` status 与 reason
- **AND** debug replay 前段 SHALL 显示回退帧画面而非 UNAVAILABLE 黑屏

#### Scenario: 无可用回退时细分不可用

- **WHEN** 回退无法产生有效帧（如媒体范围外）
- **THEN** cam_2 SHALL 保持细分不可用状态（如 `unavailable_outside_valid_interval`）
- **AND** SHALL 携带 `selection_error_ms` 等诊断字段供渲染器呈现
