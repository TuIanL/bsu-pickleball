## ADDED Requirements

### Requirement: 四人身份视觉验收指标
joint tracking 的视觉验收 SHALL 读取 `four-player-identification-quality.v1`，至少报告 confirmed roster、逐人 canonical coverage、最长缺口、identity switch、duplicate binding、cross-side contamination 与 ROI recovery contribution。硬不变量失败时整体 SHALL 不通过，即使平均覆盖率较高。

#### Scenario: 平均覆盖高但 P2 被错绑
- **WHEN** 四人平均 coverage 达标但存在 P2→P1 duplicate binding 或正式 cross-side contamination
- **THEN** 验收 SHALL 失败
- **AND** SHALL 指向具体 tick、view、source track、slot/global/canonical binding

### Requirement: Baseline 与定点片段对照
验收 runner SHALL 对同一素材的 baseline Job 与新 Job 做结构化对照，并支持人工标注定点 fixture。约第 2 秒 P2 应产生正确 P2 evidence；约第 4 秒 P2 projected/recovered evidence MUST NOT 使用 P1 bbox owner；P2 accepted trajectory MUST NOT 污染 P3/P4 side。

#### Scenario: 新 Job 定点验收通过
- **WHEN** runner 检查配置的 P2 可见与误绑片段
- **THEN** 每个 fixture SHALL 输出 expected/actual identity、bbox overlap、provenance 与 verdict
- **AND** 所有硬不变量 fixture SHALL 通过

### Requirement: Appearance enabled/disabled 消融验收
视觉验收 SHALL 对同一输入和固定配置比较 appearance disabled/enabled 结果，报告交叉片段 ID switch、reconnect 正确率、P2 coverage、duplicate/cross-side、descriptor availability 与额外耗时。appearance enabled MUST NOT 使任何硬不变量退化。

#### Scenario: 衣服颜色辅助交叉恢复
- **WHEN** P1/P2 在标注交叉片段内几何/运动代价接近，且衣服 descriptor 具有可靠区分度
- **THEN** enabled 运行 SHALL 保持或改善正确 identity continuity
- **AND** disabled/enabled 的结构化差异 SHALL 写入验收摘要
