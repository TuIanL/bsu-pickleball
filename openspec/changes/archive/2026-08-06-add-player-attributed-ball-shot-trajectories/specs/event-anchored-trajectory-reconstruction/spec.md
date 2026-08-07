# event-anchored-trajectory-reconstruction Specification

## Purpose
定义事件锚定的 2.5D 视觉重建的编排扩展：重建链接入球员上下文（`PlayerAttributionContext`），在事件仲裁后执行球员归属与 Shot 组装，输出升级后的 v2 重建产物。

## ADDED Requirements

### Requirement: 球员上下文接入
系统 SHALL 在重建链中接收球员上下文，用于击球归属与 Shot 组装，且 SHOULD 直接使用内存中的球员产物而非重新读取 JSON 文件。

#### Scenario: 内存传递球员上下文
- **WHEN** pipeline 执行重建链
- **THEN** 球员渲染轨迹、姿态帧与跟踪叠加帧 SHALL 直接以内存对象传入重建入口
- **AND** 入口 SHALL 构造 `PlayerAttributionContext` 供归属模块消费

#### Scenario: 无球员上下文时降级
- **WHEN** 球员上下文不可用（如单打简版任务或跟踪失败）
- **THEN** 重建链 SHALL 仍完成事件切段与 2.5D 重建
- **AND** 击球事件 SHALL 输出 `hitter_player_id = null` 与 `ownership_status = unassigned/not_applicable`，MUST NOT 伪造归属

### Requirement: 击球事件时间窗对齐
系统 SHALL 在事件仲裁与归属之间保持时间一致性，归属时间窗以事件时间戳为基准。

#### Scenario: 归属使用事件时间戳
- **WHEN** 击球候选进入归属阶段
- **THEN** 归属 SHALL 以候选 `timestamp_sec` 为基准查询接触时间窗
- **AND** 归属结果 SHALL 关联回原候选，保证 `attributed_frame_index` 与候选事件一致

### Requirement: serve 事件播种
系统 SHALL 将 serve 事件的 `player_id` 传递到 serve_reset 边界事件，供 Shot 播种使用。

#### Scenario: serve player_id 补传
- **WHEN** serve 事件携带 `player_id` 且置信度达标
- **THEN** 转换后的 serve_reset 事件 SHALL 保留该 `player_id`
- **AND** Shot 组装 SHALL 使用该 `player_id` 播种新 Shot

### Requirement: v2 产物输出
系统 SHALL 输出升级后的重建产物，`schema_version` 为 `reconstructed_ball_trajectory.v2`，包含球员名单、事件归属与 Shot 信息。

#### Scenario: 产物含球员名单
- **WHEN** 系统输出 v2 产物
- **THEN** 产物顶层 SHALL 包含 `player_roster`，列出 `player_id`、`render_slot` 与 `initial_side`

#### Scenario: 产物含 Shot 归属
- **WHEN** 系统输出 v2 产物
- **THEN** 每个飞行段 SHALL 包含 `shot_id`、`hitter_player_id`、`hitter_render_slot`、`ownership_status`、`ownership_confidence` 与 `ownership_source_event_id`

#### Scenario: 重建失败降级
- **WHEN** 重建链异常
- **THEN** 产物 SHALL 输出 `status = failed` 且不阻断整个分析任务
