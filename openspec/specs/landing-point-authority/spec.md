# landing-point-authority Specification

## Purpose
TBD - created by archiving change add-multiview-3d-ball-reconstruction. Update Purpose after archive.
## Requirements
### Requirement: 落点权威来源定义（reference-view bounce）
系统 SHALL 以 **reference-view confirmed bounce** 作为 bounce 事件权威来源（复用现有 BounceDetector，不在本阶段重写），经 canonical clock 定夺 bounce 的 `take_timestamp` 后，在 Cam2 于 ± tolerance 内寻找最近 accepted ball evidence，据此产出落点（不得从 3D 曲线与 `z=0` 交点倒推）。

#### Scenario: 双视角落点融合
- **WHEN** reference-view 确认 bounce，且 Cam2 在 ± tolerance 内亦存在 accepted ball evidence
- **THEN** 系统 SHALL 计算落点：`w1·H1(p1) + w2·H2(p2)`（按 geometry_quality 加权）
- **AND** `landing_source` SHALL 为 `dual_view_ground_fused`
- **AND** `landing_validity` SHALL 为 `high`（文档可注解 `court_plane_metric_estimate`，避免"精确测量"暗示）

#### Scenario: 仅 reference 可用
- **WHEN** reference-view 确认 bounce，但 Cam2 在 ± tolerance 内无 accepted ball evidence
- **THEN** 系统 SHALL 用 reference-view 单视角 `pixel → H → court(x,y)` 产出落点
- **AND** `landing_source` SHALL 为 `single_view_ground`

#### Scenario: 均无 evidence
- **WHEN** bounce 已被 reference-view 确认，但两视角均无合格地面映射证据
- **THEN** `landing_point` SHALL 标记 `unavailable`

#### Scenario: 不依赖 3D 曲线
- **WHEN** 系统确认 bounce 时刻
- **THEN** 落点 SHALL 由地面 Homography 直接融合得到
- **AND** SHALL NOT 通过求解"3D 曲线与 z=0 交点"得到

### Requirement: 落点为最高可信正式指标
系统 SHALL 将落点定义为最高可信度正式指标，即使三维球路或球速不可用，落点仍应可用。

#### Scenario: 三维不足不影响落点
- **WHEN** 某次分析 3D 重构不足或球速 unavailable
- **THEN** 落点 `landing_point` SHALL 仍为 available
- **AND** 落点 SHALL 作为"双方落区/距底线距离"等高价值输出的来源

### Requirement: bounce 事件权威不重写检测器
系统 SHALL 在本 Change 内以 reference-view confirmed bounce 为落点事件权威，不重写或替换现有 BounceDetector。

#### Scenario: 复用现有检测
- **WHEN** 系统确立落点事件权威
- **THEN** 权威 SHALL 来自 reference-view 的既有 confirmed bounce 检测
- **AND** 以 `3D z≈0 + vz 符号变化` 升级 bounce 权威 SHALL 留待后续数据成熟后的单独 Change
- **AND** 落点跨视角时序 SHALL 复用 canonical clock 的同步映射定夺 bounce 参考时刻

