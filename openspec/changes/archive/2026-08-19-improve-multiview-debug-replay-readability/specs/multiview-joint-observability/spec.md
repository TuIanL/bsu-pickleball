## ADDED Requirements

### Requirement: Display-only 帧标注未执行跟踪

Debug Replay 中状态为 `available_extrapolated` 或历史 `fallback_valid_start` 的 view 帧（仅用于显示、该 tick 未执行 perception / tracker 未 step）SHALL 在画面上叠加明确的固定标识（如 `DISPLAY ONLY · TRACKING NOT STEPPED`），区分"此帧未运行跟踪"与"检测漏检"两种完全不同的语义。此类帧 SHALL NOT 绘制或伪造任何 candidate/formal bbox，SHALL NOT 将空 `detections` 呈现为算法漏检。既有要求（显示真实源帧、叠加 status 标记、不显示 UNAVAILABLE 面板）SHALL 保持不变。

#### Scenario: 外推帧显示未跟踪横幅

- **WHEN** trace 某 tick 的 cam-2 状态为 `available_extrapolated`（或 `fallback_valid_start`）且含 `source_frame_index`
- **THEN** debug replay SHALL 显示该真实源帧画面并叠加 `DISPLAY ONLY · TRACKING NOT STEPPED` 类标识
- **AND** 画面 SHALL NOT 出现任何检测框（formal 或候选）

#### Scenario: 进入 available tick 后横幅消失

- **WHEN** 同一 view 在后续 tick 状态变为 `available`（perception 实际执行）
- **THEN** 该标识 SHALL 不再显示
- **AND** 检测框显示 SHALL 恢复 formal `detections`（及可选 `candidate_detections`）驱动的正常语义

#### Scenario: 与候选层语义不混淆

- **WHEN** 用户在 replay 前段看到 cam-2 无框且带 DISPLAY ONLY 标识、随后在 available tick 看到 cam-2 出现 `candidate` 弱框
- **THEN** 两种状态 SHALL 可视觉区分（横幅 vs 候选框）
- **AND** SHALL NOT 在 display-only tick 中以候选框形式伪造"已检测"表象
