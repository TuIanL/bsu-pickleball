## ADDED Requirements
### Requirement: 飞行段边界优先级
系统 SHALL 按固定优先级把轨迹切分为飞行段，每个边界产生新的 `segment_id`。

#### Scenario: 按优先级切分
- **WHEN** 系统确定切段边界
- **THEN** 边界优先级 SHALL 依次为：`confirmed_hit`、`confirmed_bounce`、`long_tracking_loss`、`high_confidence_serve_reset`、`end_of_stream`
- **AND** 每遇到一个边界 SHALL 生成一个新的 `segment_id`

#### Scenario: 击球边界
- **WHEN** 事件仲裁层确认一个 `confirmed_hit`
- **THEN** 该时刻 SHALL 作为飞行段边界
- **AND** 击球前后生成两个不同的飞行段

#### Scenario: 弹地边界
- **WHEN** 检测到 `confirmed_bounce`
- **THEN** 该时刻 SHALL 作为飞行段边界
- **AND** 弹地前后生成两个不同的飞行段

#### Scenario: 长时间丢失边界
- **WHEN** 连续缺失帧数超过配置的长时间丢失阈值
- **THEN** 该丢失点 SHALL 作为飞行段边界
- **AND** 后端 MUST NOT 跨该边界拟合或连接轨迹

#### Scenario: 高可信 serve 重置边界
- **WHEN** 出现高可信 serve 事件
- **THEN** 该 serve SHALL 关闭此前尚未结束的飞行段并开启新的球路上下文
- **AND** 边界原因 SHALL 记录为 `serve_reset`
- **AND** 缺失 serve 事件时系统仍依靠击球、弹地与长时间丢失完成切分

#### Scenario: 流结束
- **WHEN** 轨迹数据到达视频流末尾
- **THEN** 最后一个未关闭的飞行段 SHALL 以 `end_of_stream` 结束

### Requirement: 段间共享锚点
系统 SHALL 让相邻飞行段共享同一事件锚点，保证数据上硬切段、几何上连续。

#### Scenario: 弹地前后共享锚点
- **WHEN** 一个 `confirmed_bounce` 切分出前后两个飞行段
- **THEN** 前段的 `end_anchor_id` SHALL 等于后段的 `start_anchor_id`
- **AND** 两个段 SHALL 分别独立拟合与渲染，不共享同一条拟合曲线或样条

#### Scenario: 击球前后共享接触位置
- **WHEN** 一个 `confirmed_hit` 切分出前后两个飞行段
- **THEN** 两段 SHALL 允许速度与方向突变
- **AND** 两段 SHALL 共享同一个接触位置锚点，不显示空间空隙

### Requirement: 语义断开与几何连续的分离
系统 SHALL 区分"语义断开"与"几何断裂"，只有特定边界需要视觉上真正断开。

#### Scenario: 不需要几何断裂的边界
- **WHEN** 边界是击球或弹地且两侧均有连续有效重建点
- **THEN** 前端 SHALL 保持几何连续（共享锚点位置），仅作为独立段渲染

#### Scenario: 需要几何断裂的边界
- **WHEN** 边界为长时间检测丢失、身份重建无法证明同一颗球、回合结束或跨越无法解释的数据空洞
- **THEN** 前端 SHALL 视觉上真正断开，不跨边界连线

#### Scenario: 短缺失用虚线连接
- **WHEN** 两个有效重建点之间存在短时间缺失
- **THEN** 系统 SHALL 允许以模型预测连接并标记为 `model_predicted`
- **AND** 前端 SHALL 以虚线样式区分推算点

### Requirement: 飞行段确定性标识
系统 SHALL 为每个飞行段生成确定性且可追溯的标识。

#### Scenario: 段 ID 确定
- **WHEN** 同一输入重复运行切分
- **THEN** 每个飞行段的 `segment_id` 及起止事件引用 SHALL 完全一致
- **AND** 段 ID SHALL 引用起始与结束事件的 ID（如 `rally_3:flight_2` 或 `flight_2` 依赖上下文可用性）

### Requirement: 飞行段上下文保留
系统 SHALL 保留每个飞行段的上下文，包括起止事件类型、边界原因与锚点引用。

#### Scenario: 段上下文完整
- **WHEN** 输出一个飞行段
- **THEN** 段 SHALL 包含 `start_event_id`、`end_event_id`、`start_event_type`、`end_event_type` 与 `boundary_reason`
- **AND** 缺少权威 rally_id 时 SHALL 置为 `null`，不伪造回合归属
