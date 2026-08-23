# player-appearance-identity-cue Specification

## Purpose
TBD - created by archiving change stabilize-four-player-identification. Update Purpose after archive.
## Requirements
### Requirement: 衣服分区外观描述子
系统 SHALL 只从 detector-backed 人体 bbox 提取球员外观描述子，分别表示上衣与下装区域的 HSV/Lab 颜色分布、颜色 moments 和可选粗纹理，并携带 bbox clipping、有效像素数、blur、brightness、saturation、occlusion 与综合 quality。系统 SHALL 优先使用 pose 划分 torso/legs；pose 不可用时 SHALL 使用明确版本化的 bbox 相对分区。

#### Scenario: 清晰完整人体框产生描述子
- **WHEN** detector bbox 尺寸充分、未严重截断且上衣/下装有效像素达到阈值
- **THEN** extractor SHALL 输出 upper/lower descriptor、quality 与 extractor version
- **AND** SHALL 排除 bbox 边缘背景和可识别的皮肤高概率像素

#### Scenario: 投影框或低质量 crop
- **WHEN** entity 仅为 `cross_view_projected`/`predicted_only`，或 bbox 严重截断、过暗、过曝、模糊、像素不足
- **THEN** appearance SHALL 标记 unavailable/low_quality
- **AND** SHALL NOT 用背景色或投影框生成身份特征

### Requirement: Tracklet 与 PlayerSlot 外观模板生命周期
系统 SHALL 为 source tracklet 维护短期 descriptor gallery，并为 confirmed PlayerSlot 维护质量加权的稳健长期 template。长期 template 只能由 `confirmed_observed`、非歧义、高质量样本限幅更新；lost、projected、interpolated、ambiguous、duplicate、cross-side 与 reconnect probation 样本 MUST NOT 更新模板。

#### Scenario: 正常同一球员持续观测
- **WHEN** confirmed P2 连续产生高质量 detector-backed descriptor
- **THEN** P2 template SHALL 以质量加权 robust EMA/medoid 更新
- **AND** SHALL 记录 template age、accepted update count 与版本

#### Scenario: 疑似换人帧不污染模板
- **WHEN** P2 reconnect candidate 与 incumbent template 差异大且其他身份证据有歧义
- **THEN** candidate descriptor SHALL 只参与候选比较
- **AND** P2 长期 template SHALL 冻结，直至多帧确认完成

### Requirement: Appearance 仅作为受质量控制的软证据
appearance distance SHALL 只在几何、运动、side、尺度与一对一 hard gate 通过的候选之间参与排序。权重 SHALL 由 descriptor quality、模板 discriminative margin 与 camera profile confidence 派生；衣服颜色相似或质量不足时权重 SHALL 自动降为零。appearance MUST NOT 单独创建身份、绕过 hard gate 或触发单帧身份切换。

#### Scenario: 几何不可行但衣服颜色相似
- **WHEN** candidate 与 P2 衣服 descriptor 高度相似但位于几何 hard gate 外或属于错误 side
- **THEN** candidate SHALL 被拒绝
- **AND** appearance similarity SHALL NOT 改变该结果

#### Scenario: P1/P2 交叉且其他代价接近
- **WHEN** 两个候选均通过 hard gate、运动/几何代价接近且高质量 appearance 对 incumbent 有稳定区分度
- **THEN** appearance MAY 作为排序 tie-breaker
- **AND** 绑定切换仍 SHALL 满足连续多帧和 ambiguity margin

#### Scenario: 四人衣服颜色近似
- **WHEN** 本场四个 template 的 pairwise discriminative margin 低于阈值
- **THEN** appearance 权重 SHALL 降为零或标记 non_discriminative
- **AND** 系统 SHALL 回退到几何、运动、side 与多帧连续证据

### Requirement: 跨摄颜色归一化与隐私边界
跨摄 appearance 比较 SHALL 使用带 confidence 的 camera color profile；profile 样本不足或残差超限时 SHALL 禁用跨摄颜色代价。同摄比较不受此限制。系统默认 SHALL 只持久化数值 descriptor 质量/相似度/裁决贡献，不持久化人脸 embedding 或原始衣服 crop。

#### Scenario: 两台相机白平衡不同且 profile 有效
- **WHEN** camera profile 由同步中性区域或 confirmed paired observation 得到足够样本且残差达标
- **THEN** 系统 SHALL 先归一化再计算跨摄 appearance distance
- **AND** 诊断 SHALL 记录 profile confidence 与版本

#### Scenario: Camera profile 不可用
- **WHEN** profile 样本不足或校正残差超过阈值
- **THEN** 跨摄 appearance 权重 SHALL 为零
- **AND** SHALL NOT 用未经校正的颜色拒绝或切换 global identity

