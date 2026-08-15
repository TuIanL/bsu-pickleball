## ADDED Requirements

### Requirement: Debug replay 帧选择与 clock 回退一致

Debug replay 渲染 SHALL 以 trace 中每 tick 的 `source_frame_index` 与 `frame_status` 为准。若 clock 回退策略生效，trace 前段 view SHALL 为回退帧且 status 标记 fallback；渲染器 SHALL 显示回退帧画面并叠加对应状态标记，SHALL NOT 显示 UNAVAILABLE 面板。

#### Scenario: 回退帧正常渲染

- **WHEN** trace 前段 cam_2 status 为 fallback 且含 `source_frame_index`
- **THEN** debug replay SHALL 显示该回退帧画面
- **AND** 画面叠加 SHALL 标注 fallback 状态

#### Scenario: 细分不可用仍清晰呈现

- **WHEN** cam_2 仍为不可用状态（无回退可用）
- **THEN** debug replay SHALL 显示 UNAVAILABLE 面板与结构化原因
- **AND** SHALL 包含 `selection_error_ms` 等诊断信息
