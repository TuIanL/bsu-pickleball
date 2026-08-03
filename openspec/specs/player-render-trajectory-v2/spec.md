# player-render-trajectory-v2

## Purpose

定义版本化球员渲染轨迹 artifact 的身份槽位、分段、投影质量、样式快照和前端兼容归一化规则。

## Requirements

### Requirement: Artifact 提供渲染身份槽位

`player_render_trajectory.v2` SHALL 为每个球员分配稳定的 `render_slot`（`slot_1` 至 `slot_4`），该槽位不随 side 变化、track ID 更换或 identity_epoch 递增而改变。`MAX_RENDER_SLOTS` 固定为 4，对应产品模式为单打 2 人或双打 4 人。

#### Scenario: 同一球员跨 track ID 保持相同 render_slot

- **WHEN** 同一 player_id 跨越多个 source_track_id
- **THEN** 所有样本的 `render_slot` MUST 保持一致
- **AND** identity_epoch 变化不改变 render_slot

#### Scenario: 球员换边后 render_slot 不变

- **WHEN** 球员从 near side 移动到 far side
- **THEN** `render_slot` MUST 保持不变
- **AND** `side` 字段 MUST 反映当前帧的空间位置

#### Scenario: observed_player_count ≤ 4 时分配唯一 slot

- **WHEN** PostProcessor 在全量输入中检测到 N 个唯一 player_id（N ≤ 4）
- **THEN** 系统 MUST 为每个 player_id 分配一个唯一 render_slot
- **AND** slot 分配在完整 artifact 内不可变

#### Scenario: 球员数量超过 4 时报错且仅影响渲染 artifact

- **WHEN** observed_player_count > 4
- **THEN** 系统 MUST 抛出 `RenderSlotOverflowError`
- **AND** 该异常 MUST 被 visualization/post-processing 阶段捕获
- **AND** `player-render-trajectories` artifact MUST 标记为 failed
- **AND** tracking、ball、report 等其他 artifact MUST 不受影响

#### Scenario: slot 分配具有确定性

- **WHEN** 同一组输入由 PostProcessor 重复处理
- **THEN** 每个 player_id 的 render_slot MUST 保持一致（给定确定性的 first_reliable_frame）

### Requirement: Artifact 提供分段信息

`player_render_trajectory.v2` SHALL 将球员轨迹划分为渲染 segment，每个样本携带 `segment_id`，segment metadata 携带 `break_before` 原因。

#### Scenario: identity_epoch 变化产生新 segment

- **WHEN** 同 player_id 的 identity_epoch 从 N 变为 N+1
- **THEN** 系统 MUST 创建新 segment
- **AND** `segment.break_before` MUST 为 `identity_reset` 或 `identity_reassigned`

#### Scenario: 可见性 gap 超越阈值但不改变 identity_epoch

- **WHEN** 两帧之间时间 gap > `max_visible_gap_seconds`
- **AND** identity_epoch 不变
- **THEN** 系统 MUST 创建新 segment
- **AND** `segment.break_before` MUST 为 `visible_gap`
- **AND** identity_epoch MUST 保持不变

#### Scenario: 普通 track ID 碎片重连不产生新 segment

- **WHEN** 同一 player_id 在两个连续帧之间的 source_track_id 发生变化
- **AND** identity_epoch 和时间 gap 均在阈值内
- **THEN** 系统 MUST NOT 创建新 segment
- **AND** segment_id MUST 保持不变

#### Scenario: segment_id 格式稳定可复现

- **WHEN** 同一输入由 PostProcessor 重复处理
- **THEN** 所有 segment_id MUST 保持一致
- **AND** segment_id MUST 使用确定性格式（如 `{player_id}:e{epoch}:s{segment_index}`）

### Requirement: Artifact 携带投影质量字段

`player_render_trajectory.v2` 中的每个样本 SHALL 包含 `projection_status`、`projection_confidence`、`footpoint_method` 字段，供前端对低质量点做样式区分。

#### Scenario: 观测样本保留投影质量

- **WHEN** `source` 为 `detected`
- **THEN** `projection_status` MUST 反映该帧的投影结果（如 `inside_court`、`outside_court_visible`、`projection_failed`）
- **AND** `projection_confidence` MUST 反映投影置信度
- **AND** `footpoint_method` MUST 反映脚点估计方法

#### Scenario: 插值样本的投影质量字段为空

- **WHEN** `source` 为 `linear_interpolated` 或其他插值类型
- **THEN** 投影质量字段 MAY 为 null
- **AND** 前端 MUST 能安全处理 null 值

### Requirement: Artifact 携带 style_profile 和 segmentation_profile 快照

`player_render_trajectory.v2` SHALL 在顶层 `style_profile` 和 `segmentation_profile` 两个独立字段中包含生成时使用的视觉主题和分段参数快照。

#### Scenario: style_profile 包含颜色映射和渲染参数

- **WHEN** artifact 被生成
- **THEN** `style_profile.players` MUST 包含 `slot_1` 至 `slot_4` 的 hex 颜色
- **AND** `style_profile.ball` MUST 包含球轨迹颜色
- **AND** `style_profile.bounce` MUST 包含弹跳标记颜色
- **AND** `style_profile` MUST 包含 `player_trail_seconds`、`ball_trail_seconds`、`bounce_display_seconds`
- **AND** `style_profile` MUST 包含 `radius.min_px`、`radius.max_px`

#### Scenario: segmentation_profile 包含分段算法参数

- **WHEN** artifact 被生成
- **THEN** `segmentation_profile` MUST 包含 `jump_threshold_ft`、`max_visible_gap_seconds`
- **AND** `segmentation_profile.version` MUST 独立于 `style_profile.version`

#### Scenario: 修改颜色不影响分段参数

- **WHEN** 主题资源文件仅修改颜色值
- **AND** segmentation threshold 值不变
- **THEN** `segmentation_profile` MUST 与修改前一致
- **AND** 同一组输入生成的 segment 边界 MUST 不变

#### Scenario: 旧 job style_profile 缺失时使用前端 fallback

- **WHEN** artifact 中 style_profile 字段为 null
- **THEN** 前端 MUST 使用内置 `DEFAULT_COURT_VISUAL_THEME_V1`
- **AND** 前端 MUST NOT 报错或降级到无颜色状态

### Requirement: 扁平 samples 数组为唯一数据真源

`player_render_trajectory.v2` SHALL 使用扁平 `samples` 数组存储所有坐标点，`players` 和 `segments` 仅保存元数据引用，不重复存储坐标。

#### Scenario: samples 包含完整逐帧坐标

- **WHEN** artifact 被序列化
- **THEN** `samples` MUST 为扁平数组，每个元素包含 `x_ft`、`y_ft`、`frame_index`、`timestamp_seconds`
- **AND** `players` 和 `segments` MUST NOT 嵌套坐标数据

#### Scenario: segment_id 建立 sample 与 segment 的关联

- **WHEN** client 按 segment 分组渲染
- **THEN** client SHALL 通过 `sample.segment_id` 与 `segment.segment_id` 的等值关系建立关联
- **AND** client MUST NOT 从嵌套结构中提取 segment 内的点

#### Scenario: segment 元数据不依赖连续数组范围

- **WHEN** samples 为多球员交错的扁平序列（首屏 player_1 和 player_2 各占奇偶 sequence_index）
- **THEN** `RenderSegmentMetadata` MUST NOT 包含 `start_sequence_index` 或 `end_sequence_index`
- **AND** consumer MUST 通过 `sample.segment_id` 建立与 segment 的关联

### Requirement: 前端提供 v1/v2 归一化函数

前端 SHALL 提供 `normalizePlayerRenderTrajectory()` 函数，接受 v1 或 v2 raw artifact，输出 `NormalizedPlayerRenderTrajectory`（所有字段必填）。

#### Scenario: v2 artifact 直接映射

- **WHEN** 输入 schema_version 为 `player-render-trajectory.v2`
- **THEN** `render_slot` 和 `segment_id` MUST 直接取自 artifact 字段
- **AND** normalizer MUST NOT 重新计算 render_slot

#### Scenario: v1 artifact 降级兼容

- **WHEN** 输入为旧版 artifact（无 `render_slot`、`segment_id`、`players`、`segments`）
- **THEN** normalizer MUST 按 player_id natural sort 在前端分配临时 render_slot
- **AND** normalizer MUST 按 (player_id, identity_epoch) 分组后根据时间 gap 推导临时 segment
- **AND** v1 segment_id 格式 MUST 为 `legacy:{player_id}:e{epoch}:s{segment_index}`
- **AND** 同 epoch 内因 gap 产生多个 segment 时 MUST 使用不同 segment_index
- **AND** 前端分配的 render_slot 仅用于当前页面会话，不得写回后端

#### Scenario: 缺失 style_profile 时使用默认值

- **WHEN** artifact 不包含 style_profile 字段
- **THEN** normalizer MUST 将内置 `DEFAULT_COURT_VISUAL_THEME_V1` 写入输出
