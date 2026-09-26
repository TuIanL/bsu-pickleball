## ADDED Requirements

### Requirement: Shot Landing 依附 canonical Shot 身份

系统 SHALL 以 `shot-rally-events.v1` 中的 `ShotEvent.shot_id` 为 Shot Landing 的唯一 Shot 身份权威，并且 SHALL NOT 在 Landing Composer 中创建、重新编号、推断或替换 canonical Shot 身份。

#### Scenario: 通过 segment 引用精确关联
- **WHEN** canonical Shot 的 `trajectory.segment_ids` 引用多个 reconstructed segments
- **THEN** Composer SHALL 只在这些 segment 中寻找该 Shot 的落点证据
- **AND** SHALL 使用 `Segment.end_event_id == Event.event_id` 关联事件

#### Scenario: 关联缺失时不做最近邻猜测
- **WHEN** Shot 引用的 segment 或 segment 引用的 event 不存在
- **THEN** 该 Shot Landing SHALL 降级为 `unavailable`
- **AND** diagnostics SHALL 记录缺失引用
- **AND** Composer MUST NOT 使用时间最近邻或重跑 `BallShotAssembler` 补链

### Requirement: 每个 Shot 仅选取首次正式 Bounce

系统 SHALL 将 Shot 引用的 segments 按正式事件时间和稳定 segment ID 排序，并将第一个 `end_event_type == bounce` 的正式事件作为该 Shot 的 Landing 证据。

#### Scenario: Hit 后首次 Bounce
- **WHEN** Shot 的事件序列为 `Hit → Bounce → Hit`
- **THEN** 第一个正式 Bounce SHALL 成为该 Shot 的 Landing
- **AND** Landing SHALL 保留该 Bounce 的 event ID、frame index 和 timestamp

#### Scenario: 对手截击前未弹地
- **WHEN** Shot 的事件序列为 `Hit → Hit` 且中间没有正式 Bounce
- **THEN** `landing_status` SHALL 为 `no_bounce_before_next_contact`
- **AND** 该状态 MUST NOT 被计为落点检测失败

#### Scenario: Shot 内存在多次 Bounce
- **WHEN** 同一 Shot 关联到两个或以上正式 Bounce
- **THEN** Composer SHALL 只取第一个正式 Bounce
- **AND** 后续 Bounce SHALL NOT 覆盖 first landing

#### Scenario: 只有诊断候选
- **WHEN** Bounce 已被 suppressed/rejected 或只存在于 diagnostics 而不在正式 segment/event 关系中
- **THEN** Composer SHALL NOT 将该候选升级为 Landing
- **AND** 无其他正式 Bounce 时 SHALL 输出 `ambiguous_bounce` 或 `unavailable` 并记录原因

#### Scenario: Shot 以 Loss 或 EOS 结束
- **WHEN** Shot 在没有正式 Bounce 或下一次接触的情况下以 Loss 或 EOS 结束
- **THEN** `landing_status` SHALL 为 `unavailable`

### Requirement: 落点可用性与空间分类正交

每条 Shot Landing SHALL 分别表达 `landing_status`、`court_location` 和 `target_relation`。`landing_status` SHALL 限定为 `available | no_bounce_before_next_contact | bounce_without_court_coordinate | ambiguous_bounce | unavailable`；`court_location` SHALL 限定为 `inside_court | outside_court | unknown`；`target_relation` SHALL 限定为 `target_half | own_half | unknown`。

#### Scenario: 可用界外落点
- **WHEN** 正式 Bounce 有有限球场坐标且该点明确在球场外
- **THEN** `landing_status` SHALL 为 `available`
- **AND** `court_location` SHALL 为 `outside_court`
- **AND** 原始英尺坐标 SHALL 保留且 MUST NOT 被 clamp 到边线

#### Scenario: Bounce 缺少 court coordinate
- **WHEN** 正式 Bounce 存在但其 court coordinate 缺失或非有限数
- **THEN** `landing_status` SHALL 为 `bounce_without_court_coordinate`
- **AND** `court_location` 与 `target_relation` SHALL 为 `unknown`

#### Scenario: 边线不确定带
- **WHEN** 落点到球场边界的距离不大于已知 calibration uncertainty 或缺省 0.1 ft 保守容差
- **THEN** `court_location` SHALL 为 `unknown`
- **AND** 系统 SHALL NOT 将该几何分类宣告为比赛界内外裁判

### Requirement: 保留落点绝对球场坐标与时间证据

对于坐标可用的 Landing，系统 SHALL 保留 `landing_x_ft`、`landing_y_ft`、`frame_index` 和 `timestamp_ms`，并将 20 ft × 44 ft、球网 `y=22 ft` 的 coordinate metadata 写入 artifact。

#### Scenario: 保留绝对几何真值
- **WHEN** 正式 Bounce 提供 court coordinate
- **THEN** Landing SHALL 原样保留有限英尺坐标
- **AND** 分区修改 SHALL NOT 要求重新运行球检测

#### Scenario: 时间单位与 canonical 事件一致
- **WHEN** Composer 将 Bounce timestamp 写入 Shot Landing
- **THEN** 公开 `timestamp_ms` SHALL 以毫秒表达
- **AND** `frame_index` SHALL 保留为原视频帧证据

### Requirement: 目标半场标准化 fail closed

系统 SHALL 优先使用击球者在 `contact_ms` 附近的冻结 canonical 球员球场轨迹位置确定击球侧，仅在该证据不可用时才允许使用 Shot 轨迹方向。系统 MUST NOT 通过落点所在半场反推击球侧。

#### Scenario: 使用接触时动态球员位置
- **WHEN** `hitter_player_id` 存在，且在 `contact_ms ± 250 ms` 内存在该 canonical Player_N 的有效球场位置
- **THEN** 系统 SHALL 根据该位置的 `y < 22` 或 `y > 22` 确定击球侧
- **AND** `canonicalization_basis` SHALL 为 `hitter_position_at_contact`

#### Scenario: 回退到轨迹方向
- **WHEN** 接触时击球者位置不可用，但 Shot 起点到首次 Bounce 的纵向净位移超过版本化方向证据门限
- **THEN** 系统 MAY 由该方向确定目标半场
- **AND** `canonicalization_basis` SHALL 为 `trajectory_direction`

#### Scenario: 方向证据不足
- **WHEN** 接触时位置和轨迹方向均不足
- **THEN** `canonicalization_basis` SHALL 为 `unavailable`
- **AND** `target_x_ft`、`target_y_ft`、`landing_u`、`landing_v`、`zone_12` 和 `zone_6` SHALL 为 null

#### Scenario: 近端目标半场旋转
- **WHEN** 确定目标半场为 near side
- **THEN** `orientation_transform` SHALL 为 `rotate_180`
- **AND** `target_x_ft = 20 - landing_x_ft`
- **AND** `target_y_ft = 44 - landing_y_ft`

#### Scenario: 远端目标半场保持方向
- **WHEN** 确定目标半场为 far side
- **THEN** `orientation_transform` SHALL 为 `identity`
- **AND** `target_x_ft = landing_x_ft`
- **AND** `target_y_ft = landing_y_ft`

### Requirement: `project12.v1` 分区映射可版本化且确定

系统 SHALL 将目标半场横向划分为 `L=[0,1/3)`、`C=[1/3,2/3)`、`R=[2/3,1]`，将距球网纵向距离划分为 `K=[0,7)`、`T=[7,12)`、`D=[12,17)`、`VD=[17,22]` ft，并以 `project12.v1` 记录 profile 版本和边界 basis。

#### Scenario: 目标半场内的落点进入十二区
- **WHEN** Landing 同时满足 `available`、`inside_court`、`target_half` 且 `u/v` 可用
- **THEN** 系统 SHALL 生成一个且仅一个 `zone_12`
- **AND** SHALL 记录 `zone_12_profile=project12.v1`

#### Scenario: 分区边界归属确定
- **WHEN** 落点恰好位于横向 1/3、2/3 或纵向 7、12、17 ft 边界
- **THEN** 该点 SHALL 归入边界之后的区间
- **AND** 1.0 与 22 ft 上界 SHALL 分别归入 R 和 VD

#### Scenario: 界外、己方或不确定落点不进入分区
- **WHEN** Landing 不满足 `available + inside_court + target_half` 或无法标准化
- **THEN** `zone_12` 和 `zone_12_id` SHALL 为 null

#### Scenario: 论文六区未配置
- **WHEN** `paper6.v1` 的来源和边界尚未冻结
- **THEN** `zone_6` 和 `zone_6_profile` SHALL 为 null
- **AND** 系统 SHALL NOT 使用临时边界生成 FZ1–FZ6

### Requirement: Shot Landing 保留完整 provenance 并确定性生成

每条 Landing SHALL 保留 `landing_id`、`shot_id`、`rally_id`、`ordinal_in_rally`、`bounce_event_id`、`hitter_player_id`、`shot_stage`、`source_segment_id`、`source_event_id`、`orientation_transform`、profile ID、`landing_source`、质量字段与 `source_artifacts`。相同输入与相同 profile 版本 SHALL 产生相同的 Landing ID、值与排序（`generated_at` 除外）。

#### Scenario: 落点可追溯到原始证据
- **WHEN** 生成一条可用 Landing
- **THEN** 其 `source_segment_id` 和 `source_event_id` SHALL 引用实际存在的正式证据
- **AND** `source_artifacts` SHALL 至少包含 canonical Shot 和 reconstructed trajectory 来源

#### Scenario: 相同输入重复生成
- **WHEN** 同一 job 以相同输入和 profile 重新生成 Shot Landings
- **THEN** 除 `generated_at` 外两份 artifact SHALL 逐字段一致

### Requirement: Shot Landing 统计使用可审计分母

系统 SHALL 区分有效落点数、正式 Bounce Shot 数、无弹地 Shot 数和可进入分区落点数。比例 SHALL 保留分子、分母和样本量语义，且 SHALL NOT 生成落点水平评分。

#### Scenario: 空间可测率排除无弹地 Shot
- **WHEN** 计算空间可测率
- **THEN** 分母 SHALL 为已具有正式 Bounce 语义的 Shot 数
- **AND** 分子 SHALL 为其中拥有有限 court coordinate 的 Shot 数
- **AND** `no_bounce_before_next_contact` SHALL NOT 进入该分母

#### Scenario: 十二区占比分母
- **WHEN** 计算各 `project12.v1` 区域占比
- **THEN** 分母 SHALL 只包含成功生成 `zone_12` 的 Landing
- **AND** 界外、己方半场、方向不明和坐标不可用项 SHALL NOT 进入该分母
