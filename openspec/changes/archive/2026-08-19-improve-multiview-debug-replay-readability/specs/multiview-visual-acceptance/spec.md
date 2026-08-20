## ADDED Requirements

### Requirement: Debug trace 可选候选检测层

`joint_debug_trace.v1` 的每个 view SHALL 支持可选 debug-only 字段 `candidate_detections`。当且仅当该 tick 该 view 状态为 `available`（即 perception 实际执行）且 tracker 存在"存活但未满足 `lock_only` formal eligibility"的 track 时，生产端 SHALL 可将这些 provisional 候选写入 `candidate_detections`（每项至少含 `bbox`、`track_id`、`confidence`）。formal `detections` 的定义、来源与过滤规则 SHALL 保持不变；`candidate_detections` SHALL NOT 进入 `frame_detections`、identity、association、fusion 或任何正式分析产物。trace validator SHALL 将 `candidate_detections` 作为可选字段校验：字段缺失时 trace 仍 SHALL 通过加载；字段存在时其值 SHALL 为 list。display-only tick（未执行 perception 的 view）SHALL NOT 写入 `candidate_detections`。

#### Scenario: bootstrap 期候选被记录且与 formal 隔离

- **WHEN** 某 `available` tick 中 tracker 存活 track 包含 track A（已满足 lock eligibility）与 track B（尚未锁定）
- **THEN** trace 该 view 的 `detections` SHALL 仅含 track A
- **AND** `candidate_detections` SHALL 含 track B 的 bbox/track_id/confidence，且不含 player_id

#### Scenario: 旧 trace 无字段仍可加载

- **WHEN** 加载不含 `candidate_detections` 字段的历史 `joint_debug_trace.v1`
- **THEN** validator SHALL 通过校验
- **AND** renderer SHALL 以空候选列表渲染，行为等同现状

#### Scenario: display-only tick 不写候选

- **WHEN** 某 tick 该 view 状态为 `available_extrapolated` 或 `fallback_valid_start`（perception 未执行）
- **THEN** 该 view SHALL NOT 出现 `candidate_detections` 内容
- **AND** 该 view 的 `detections` SHALL 保持为空

#### Scenario: 候选不污染正式产物

- **WHEN** debug trace 开启且 `candidate_detections` 非空
- **THEN** 正式 `frame_detections`、`fused_player_trajectory.v2` 与 fused overlay 数据源 SHALL 不包含任何候选 track
- **AND** `eligibility_policy` SHALL 保持 `lock_only` 语义不变

### Requirement: Debug renderer 候选框与正式框区分绘制

Debug MP4 renderer SHALL 对 `candidate_detections` 与 formal `detections` 使用视觉强区分的双层绘制：候选框 SHALL 使用细线（线宽小于正式框）与弱色，标签 SHALL 统一包含 `tracker candidate` 字样（可附 track id），SHALL NOT 显示 `Player_N` 或任何 formal 身份；正式框 SHALL 保持既有高亮实线与 `Player_N` 标注不变。生产端 SHALL 按 `candidate_track_ids = live_track_ids - eligible_track_ids` 计算候选集合，同一 tick 内 `formal_track_ids ∩ candidate_track_ids` SHALL 为空（同一 track SHALL NOT 同时以候选框和正式框出现）。同一 track 在后续 tick 完成正式锁定后，其候选框 SHALL 被正式框取代。renderer SHALL 使用 `view.get("candidate_detections", [])` 容错读取，字段缺失时 SHALL 不绘制候选框。

#### Scenario: bootstrap 期看到弱候选框

- **WHEN** 某 `available` tick 的 view 中 formal `detections` 为空、`candidate_detections` 含存活 track
- **THEN** 该 view 画面 SHALL 为每个候选绘制细线弱色框并标注 `tracker candidate`
- **AND** SHALL NOT 出现 `Player_N` 标注

#### Scenario: 同一 tick 内候选与正式集合互斥

- **WHEN** 某 `available` tick 的 view 同时产生 formal `detections` 与 `candidate_detections`
- **THEN** 两个集合的 track_id SHALL 互不相交
- **AND** 生产端 SHALL 按 `live_track_ids - eligible_track_ids` 计算候选集合

#### Scenario: 正式锁定后候选被取代

- **WHEN** track 在 tick N 为候选、在 tick M（M>N）完成 lock 进入 formal `detections`
- **THEN** tick M 画面 SHALL 仅以正式框样式绘制该 track
- **AND** 该 track SHALL NOT 再出现在候选框中

### Requirement: Debug MP4 court panel 等比绘制

Debug MP4 的 canonical court panel SHALL 使用单一 px/ft 比例绘制球场，SHALL NOT 对 20 ft 与 44 ft 两个方向使用不同比例。球场 SHALL 横置显示（44 ft 为横轴、20 ft 为纵轴），保持真实 `44:20 = 2.2:1` 外观，并 SHALL 绘制外边界、网（距底线 22 ft）、两侧 NVZ line（各距网 7 ft）与两段 service centerline（NVZ 至底线区间）。canonical `(x_ft, y_ft)` 数据 SHALL 保持不变，轴交换 SHALL 仅发生在显示层。Debug MP4 整体 SHALL 保持既有四联布局与 `1280×620` 输出尺寸契约。

#### Scenario: 球场无均匀拉伸

- **WHEN** renderer 绘制 court panel
- **THEN** 横向与纵向 SHALL 使用同一 px/ft scale
- **AND** 球场外观比例 SHALL 为 2.2:1（44 ft 边显著长于 20 ft 边）

#### Scenario: 标准球场线齐全

- **WHEN** court panel 渲染完成
- **THEN** 画面 SHALL 包含外边界、网、两条 NVZ line 和两段发球中线
- **AND** 球员位置点 SHALL 按显示层轴交换映射落在新坐标系中

#### Scenario: MP4 输出尺寸不变

- **WHEN** renderer 输出 debug MP4
- **THEN** 视频 SHALL 保持 `1280×620` 四联布局
- **AND** 既有输出尺寸契约 SHALL 不因 court panel 重绘而改变
