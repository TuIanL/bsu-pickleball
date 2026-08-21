## MODIFIED Requirements

### Requirement: 叠加样式按 evidence_type 区分

视频叠加层的展示职责 SHALL 分三层：`player_id` 决定 identity hue（同一 Player 跨 evidence 恒定的主色，MUST NOT 因证据来源如 Cam2 辅助/投影/预测而改变）；`display_state` 决定 geometry topology（BOX / POINT / HIDDEN）；`evidence_type` 决定 provenance style（real / assisted / projected / predicted 的实线 / 虚线 / 透明度 / badge），MUST NOT 改变 identity hue。`evidence_type` 为 `base_observed` / `guided_observed` / `refined_observed` SHALL 用实线真实检测框；`cross_view_projected` SHALL 用虚线或半透明框（携带协同补全语义）；`predicted_only` SHALL 用淡化 footpoint / identity badge / uncertainty halo。synthetic 证据 SHALL NOT 借助颜色伪装为真实检测实线框。

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

#### Scenario: 身份色跨证据恒定

- **WHEN** 同一 `Player_N` 在 `base_observed` / `guided_observed` / `refined_observed` / `cross_view_projected` / `predicted_only` 之间切换
- **THEN** 人物主色 SHALL 保持身份色不变（`identity_color_switch_count` SHALL 为 0）
- **AND** evidence source SHALL 通过线型 / 透明度 / badge 表达

## ADDED Requirements

### Requirement: Renderer 消费 display_state 作为几何展示权威

前端人物 Overlay renderer SHALL 将 `display_state`（`REAL_BOX / ASSISTED_BOX / PROJECTED_BOX / PROJECTED_POINT / PREDICTED_POINT / HIDDEN`）作为人物几何形态（BOX / POINT / HIDDEN）的权威输入，MUST NOT 仅依赖 `evidence_type` 判断框 / 点 / 隐藏。`display_state` 存在时 SHALL 优先于 `evidence_type` 决定 geometry topology；`evidence_type` 仅决定 provenance style，MUST NOT 改变 identity hue。

#### Scenario: display_state 覆盖几何形态

- **WHEN** overlay entity 的 `display_state` 为 `PROJECTED_BOX`（真实 bbox 丢失后经迟滞降级，复用最后可靠 presentation box geometry），而同一 tick 的 `evidence_type` 为 `cross_view_projected`
- **THEN** renderer SHALL 按 `display_state` 渲染为 BOX 形态
- **AND** SHALL 按 `evidence_type` 以虚线 / 透明度表达 provenance

#### Scenario: display_state HIDDEN 不渲染

- **WHEN** overlay entity 的 `display_state` 为 `HIDDEN`
- **THEN** renderer SHALL 不渲染该球员

#### Scenario: 旧产物缺失 display_state 兼容

- **WHEN** 历史 fused overlay entity 缺失 `display_state`
- **THEN** renderer SHALL 按既有逻辑推导 legacy display_state（由 `evidence_type + bbox + footpoint` 得出）
- **AND** SHALL NOT 因字段缺失破坏解析

### Requirement: 展示几何状态与证据来源正交

Renderer MUST 使用 `display_state` 决定 BOX / POINT / HIDDEN topology，并使用 `evidence_type` 表达 provenance；两者 MUST NOT 相互重写。`player_id` SHALL 是 identity hue 的唯一 authority。`REAL_BOX` / `ASSISTED_BOX` SHALL 仅在当前 tick 存在对应真实 target-view bbox 时才为合法状态；当真实 bbox 丢失但仍有合法 presentation box 时，`display_state` SHALL 立即降级为 `PROJECTED_BOX`（复用最后可靠 presentation geometry），MUST NOT 继续输出 `REAL_BOX`。

#### Scenario: 真实 bbox 缺失不得保留 REAL_BOX

- **WHEN** `base_observed` 真实 bbox 在当前 tick 丢失，但有 donor / global projected evidence
- **THEN** `display_state` SHALL 立即变为 `PROJECTED_BOX`（复用最后可靠 presentation geometry）
- **AND** SHALL NOT 输出 `REAL_BOX`（`REAL_BOX` 仅表示当前存在真实 bbox）

#### Scenario: 三通道正交

- **WHEN** renderer 渲染一个 overlay entity
- **THEN** `player_id` SHALL 决定 identity hue、`display_state` SHALL 决定 topology、`evidence_type` SHALL 决定 provenance style
- **AND** 三者 MUST NOT 相互重写