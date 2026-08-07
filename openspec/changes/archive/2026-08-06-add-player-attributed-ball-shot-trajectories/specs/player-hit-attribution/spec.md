# player-hit-attribution Specification

## Purpose
定义击球球员归属能力：基于共享上肢证据与球—球员时空匹配，为通过事件粗门的击球候选评分并判定 `confirmed / ambiguous / unassigned`，所有归属结果仅使用 canonical `Player_N`。

## Requirements

### Requirement: 共享上肢证据索引
系统 SHALL 提供共享的上肢证据索引，从姿态帧提取 wrist/elbow 关键点坐标与运动强度，供击球归属与发球检测共同消费。

#### Scenario: 索引包含关键点坐标与运动强度
- **WHEN** 系统从姿态帧构建上肢证据索引
- **THEN** 每条证据 SHALL 包含 track_id、frame_index、timestamp_seconds、左右手腕坐标、左右肘部坐标与 `arm_motion_px_per_second`
- **AND** 关键点坐标 SHALL 仅保留可见且置信度达标的关键点

#### Scenario: 发球检测迁移到共享索引
- **WHEN** 发球检测读取上肢运动证据
- **THEN** 发球检测 SHALL 从共享索引读取 `arm_motion`，而非自行维护私有实现
- **AND** 迁移后发球检测输出 SHALL 与迁移前行为一致（回归测试保证）

### Requirement: 击球候选球员归属
系统 SHALL 对通过事件粗门的击球候选，综合球—手腕距离、球—人体框距离、上肢运动峰值、半场一致性与时间接近度评分，输出归属判定。

#### Scenario: 手腕靠近球且有运动峰值
- **WHEN** 某球员手腕在接触时间窗内最接近球的候选位置且上肢运动峰值明确
- **THEN** 归属 SHALL 判定为 `confirmed`
- **AND** 归属对象 SHALL 为该球员的 canonical `player_id`
- **AND** 归属 SHALL 记录 `attributed_frame_index`（球—手腕距离最小帧）

#### Scenario: 网前两名球员距离接近
- **WHEN** 两名候选球员检测框距离接近，但其中一名手腕运动明显更强
- **THEN** 归属 SHALL 判定为手腕运动更强的球员
- **AND** MUST NOT 仅依据"最近脚点/最近检测框"归属

#### Scenario: 证据接近无法区分
- **WHEN** 第一名候选与第二名候选评分差距低于判定余量
- **THEN** 归属 SHALL 判定为 `ambiguous`
- **AND** 归属 SHALL NOT 强制选择任意一名球员

#### Scenario: 无足够球员证据
- **WHEN** 候选附近没有可用球员证据或全部证据低于最低阈值
- **THEN** 归属 SHALL 判定为 `unassigned`
- **AND** 该击球事件 SHALL 保留 `hitter_player_id = null`

#### Scenario: 无姿态数据时降级
- **WHEN** 姿态数据不可用但球员检测框可用
- **THEN** 归属 SHALL 对剩余证据权重归一化后仍可判定
- **AND** 归属方法 SHALL 记录为不含姿态来源（如 `bbox_fused`）

### Requirement: 球—手腕距离尺度归一化
系统 SHALL 对球—手腕像素距离按球员人体尺度归一化，消除画面远近造成的尺度偏差。

#### Scenario: 远端球员不因画面尺度吃亏
- **WHEN** 球到两名候选球员手腕的像素距离相近
- **THEN** 归一化距离 SHALL 以球员检测框对角线（不低于最小尺度下限）为分母
- **AND** 画面中较小的球员 SHALL NOT 因像素尺度小而天然获得劣势

### Requirement: 非对称接触时间窗
系统 SHALL 使用以秒为单位的非对称接触时间窗查询球员证据，兼容不同帧率与 frame_stride。

#### Scenario: 时间窗内查询
- **WHEN** 击球事件时间为 t
- **THEN** 系统 SHALL 在 `[t - contact_window_before_sec, t + contact_window_after_sec]` 内查询球员姿态与跟踪证据
- **AND** 前窗 SHALL 大于后窗以容纳检测滞后（真实接触早于突变被检测到的帧）

#### Scenario: 证据帧缺失容差
- **WHEN** 候选球员在时间窗内的证据帧间隔超过配置的最大采样间隔
- **THEN** 系统 SHALL 跳过该证据或降低其权重
- **AND** MUST NOT 用超出窗口的帧推断归属

### Requirement: 发球直接播种归属
系统 SHALL 对发球事件直接使用已有 `player_id` 作为击球者，不执行普通最近球员推断。

#### Scenario: 发球事件播种
- **WHEN** 发球事件携带 canonical `player_id`
- **THEN** 该发球对应的击球归属 SHALL 直接使用该 `player_id`
- **AND** 归属方法 SHALL 记录为 `serve_seeded`

#### Scenario: 发球事件缺 player_id
- **WHEN** 发球事件未携带 `player_id`
- **THEN** 系统 SHALL 回退到普通归属流程
- **AND** 若证据不足 SHALL 判定 `unassigned`，MUST NOT 伪造归属

### Requirement: canonical 身份输出
系统 SHALL 仅输出 canonical `Player_N` 作为归属结果，瞬时 track_id 只作为证据关联键。

#### Scenario: track_id 规范化
- **WHEN** 证据使用整数或字符串形式的 track_id
- **THEN** 内部关联键 SHALL 统一为字符串形式
- **AND** 归属结果与事件字段 SHALL 只保存 canonical `player_id`

#### Scenario: 契约测试
- **WHEN** `PlayerTrajectorySample(track_id=17, player_id="Player_2")` 与 `PoseSubject(track_id="17")` 同时存在
- **THEN** 归属候选 SHALL 映射到 `Player_2`
