## ADDED Requirements

### Requirement: 叠加样式按 evidence_type 区分

视频叠加层 SHALL 按 `evidence_type` 区分呈现样式：`base_observed` / `guided_observed` / `refined_observed` 使用实线真实检测框；`cross_view_projected` 使用虚线或半透明框（携带协同补全语义）；`predicted_only` 使用淡化 footpoint / identity badge / uncertainty halo。球员颜色 SHALL 仅表示身份（同一 Player 颜色恒定），SHALL NOT 因证据来源（如 Cam2 辅助）而改变颜色。

#### Scenario: 真实观测实线

- **WHEN** `evidence_type` 为 `base_observed` / `guided_observed` / `refined_observed`
- **THEN** 叠加层 SHALL 以实线渲染该球员的 bbox
- **AND** SHALL 使用与身份一致的颜色

#### Scenario: 协同补全虚线

- **WHEN** `evidence_type` 为 `cross_view_projected`
- **THEN** 叠加层 SHALL 以虚线或半透明样式渲染
- **AND** SHALL 保持该球员身份颜色不变

#### Scenario: 预测仅光圈

- **WHEN** `evidence_type` 为 `predicted_only`
- **THEN** 叠加层 SHALL 以淡化 footpoint / identity badge / uncertainty halo 渲染
- **AND** SHALL NOT 渲染为实线检测框

### Requirement: fused overlay 播放时间解析

播放时间解析 SHALL 按 canonical `player_id`（而非本地 `track_id`）对 fused overlay 帧做前后帧插值；SHALL 支持 gap 语义：短 gap 合法插值，超过 `max_overlay_gap` SHALL 禁止跨 gap 插值；`predicted_only` 超过 TTL SHALL 立即隐藏。

#### Scenario: 按 player_id 稳定插值

- **WHEN** 播放时间位于两帧之间且同一 `player_id` 在两帧均存在
- **THEN** 叠加层 SHALL 按时间比例插值该球员 bbox / footpoint

#### Scenario: 跨 gap 禁止插值

- **WHEN** 相邻两帧间隔超过 `max_overlay_gap`
- **THEN** 叠加层 SHALL NOT 在两帧之间插值球员

#### Scenario: 预测超 TTL 隐藏

- **WHEN** `predicted_only` 球员的预测持续超过 TTL
- **THEN** 该球员 SHALL 从叠加层消失
