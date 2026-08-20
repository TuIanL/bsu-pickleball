## MODIFIED Requirements

### Requirement: 窗口开头副摄帧选择回退

当 canonical tick 落在人工锚点覆盖区间（`valid_start_seconds` / `valid_end_seconds`，本规范正式定义为 anchor evidence span——人工锚点覆盖的 reference 时间区间，不表示"在此之前 Cam-2 无对应画面"）之外时，clock 不再把"区间外"等价于"无真实画面"。clock 对区间外 tick 直接用原始 canonical 时间计算 `local = map_reference_time(calibration, t)`（MUST NOT clamp 到锚点边界），并将 `local` 与 secondary view 的媒体 PTS 范围比较：落在范围内且最近帧距离 `<= max_selection_error_seconds` → 选中最近真实帧并标记 `available_extrapolated`（带 `mapping_mode` / `extrapolation_distance_ms` / `selection_error_ms` 诊断）；落在范围内但最近帧距离 `> max_selection_error_seconds` → 标记 `unavailable_selection_error`（复用 authoritative frame-selection 质量门，外推不放松该门）；越出媒体 PTS 范围 → 标记 `unavailable_out_of_media_range`。该外推 SHALL 对称覆盖 pre-anchor（`t < anchor_start`）与 post-anchor（`t > anchor_end`）两端；低侧不再冻结于第一锚点帧，高侧只要真实媒体仍存在就不再黑屏。外推帧 MUST NOT 伪装为 authoritative `available`（status 显式区分，`build_frame_map()` 的权威 `available` 契约不变）。

#### Scenario: pre-anchor 帧正常递增

- **WHEN** canonical tick 早于 `anchor_start`（如 3.4s）但 affine 映射后的 cam_2 时间在媒体内
- **THEN** cam_2 的 `source_frame_index` SHALL 随 canonical tick 正常推进（而非固定第一锚点帧）
- **AND** status SHALL 为 `available_extrapolated`，`mapping_mode=pre_anchor_extrapolation`

#### Scenario: post-anchor 仍有真实画面

- **WHEN** canonical tick 晚于 `anchor_end`（如 58s）但 affine 映射后的 cam_2 时间仍落在媒体内
- **THEN** cam_2 SHALL 持续提供真实画面，status 为 `available_extrapolated`，`mapping_mode=post_anchor_extrapolation`
- **AND** MUST NOT 显示 UNAVAILABLE 黑屏

#### Scenario: 外推越出媒体才不可用

- **WHEN** affine 映射后的 cam_2 时间越出 secondary 媒体 PTS 范围
- **THEN** cam_2 SHALL 标记 `unavailable_out_of_media_range`
- **AND** SHALL 携带 `selection_error_ms` 等诊断字段供渲染器呈现

#### Scenario: 不 clamp 到锚点边界

- **WHEN** canonical tick 在锚点区间外
- **THEN** clock SHALL NOT 使用 `max(t, valid_start)` 之类把外推目标钳制到锚点边界
- **AND** 外推目标 SHALL 为 `map_reference_time(calibration, t)` 的真实值

#### Scenario: 无可用外推时细分不可用

- **WHEN** 外推无法产生有效帧（如映射越出媒体范围）
- **THEN** cam_2 SHALL 保持细分不可用状态（`unavailable_out_of_media_range`）
- **AND** SHALL 携带 `selection_error_ms` 等诊断字段供渲染器呈现

#### Scenario: selection error 超限不标 available_extrapolated

- **WHEN** affine 映射后的 cam_2 时间落在媒体 PTS 内，但最近真实帧距离 `abs(selection_error_seconds) > max_selection_error_seconds`
- **THEN** cam_2 SHALL 标记 `unavailable_selection_error`（复用 authoritative frame-selection 质量门）
- **AND** SHALL NOT 标记 `available_extrapolated`（外推只放宽 anchor-span authority gate，不放松 frame-selection 质量门）

## ADDED Requirements

### Requirement: 外推帧不污染 tracker 消费游标

`available_extrapolated` 帧 SHALL 携带 `source_frame_index` 并进入 trace / Debug Replay，但 SHALL NOT 推进 `last_consumed_source_frame_index`（该游标仅由 authoritative `available` 路径维护，语义是"已喂给有状态 tracker"，是 source-frame 单调不重复守卫的依据）。`MultiViewJointRun` 的 perception 主链（detector / tracker / association / fusion / recovery）因 `status != "available"` 自动跳过外推帧。即使连续两个 canonical tick 映射到同一 cam_2 源帧，外推路径 SHALL NOT 触发 `no_new_frame`（那是 `available` 路径的单调守卫），renderer 的 `cached_frame.copy()` 同帧拷贝优化仍正确工作。

#### Scenario: 外推帧不更新消费游标

- **WHEN** 某 tick secondary 为 `available_extrapolated`
- **THEN** `last_consumed_source_frame_index[secondary_view]` SHALL NOT 被更新
- **AND** 该帧 SHALL NOT 被送入 `tracker.step` / `prepare`

#### Scenario: 感知主链跳过外推帧

- **WHEN** `bundle.frame_status[view] == "available_extrapolated"`
- **THEN** `MultiViewJointRun` 的 prepare/step 与 recovery 的 `target_available` 判定 SHALL 按 `status != "available"` 跳过
- **AND** 锚点区间外 cam_2 的 `tracking_session.step/prepare` 调用次数 SHALL 为 0
