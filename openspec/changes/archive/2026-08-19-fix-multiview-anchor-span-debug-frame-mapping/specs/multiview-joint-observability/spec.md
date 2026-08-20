## MODIFIED Requirements

### Requirement: Debug replay 帧选择与 clock 回退一致

Debug replay 渲染 SHALL 以 trace 中每 tick 的 `source_frame_index` 与 `frame_status` 为准。若 clock 外推策略生效，trace 前段 view SHALL 为外推帧且 status 标记 `available_extrapolated`（或历史产物的 `fallback_valid_start`）；渲染器 SHALL 显示真实外推帧画面并叠加对应状态标记，SHALL NOT 显示 UNAVAILABLE 面板。渲染器 SHALL 兼容历史 `fallback_valid_start` 产物（旧 trace 仍渲染回退帧）。外推帧的 `source_frame_index` 在连续 canonical tick 正常递增时，渲染器 SHALL 解码对应真实帧（不再因人为 clamp 而重复同一帧）。

#### Scenario: 外推帧正常渲染

- **WHEN** trace 前段 cam_2 status 为 `available_extrapolated` 或历史 `fallback_valid_start` 且含 `source_frame_index`
- **THEN** debug replay SHALL 显示该真实帧画面
- **AND** 画面叠加 SHALL 标注对应 status

#### Scenario: 外推帧连续递增不重复冻结

- **WHEN** 连续 canonical tick 的 `available_extrapolated` 帧 `source_frame_index` 递增
- **THEN** renderer SHALL 解码对应递增真实帧，cam_2 视角 SHALL 持续运动
- **AND** MUST NOT 把同一帧重复写入多秒（不再有开头定格现象）

#### Scenario: 细分不可用仍清晰呈现

- **WHEN** cam_2 仍为不可用状态（如 `unavailable_out_of_media_range` / `unavailable_selection_error`）
- **THEN** debug replay SHALL 显示 UNAVAILABLE 面板与结构化原因
- **AND** SHALL 包含 `selection_error_ms` 等诊断信息
