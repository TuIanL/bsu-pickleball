## ADDED Requirements

### Requirement: 四人识别质量区分感知覆盖与身份确认

真实双打 Job 的质量产物 SHALL 分别报告原始人体检测、local track、global candidate/正式观测、metric-eligible 轨迹及冻结名册确认的逐端/逐人计数、覆盖率、最长缺口和拒绝原因。`mapping_confirmed=false` 导致的 canonical coverage 为零 SHALL 与原始检测为零区分。质量 verdict SHALL 分别指出感知缺失、同端集中、名册绑定失败、长时间无球员及硬不变量失败；`status=completed` 不得被解释为四人识别通过。

#### Scenario: 有检测但身份未确认

- **WHEN** 两机位存在大量人体检测与 global 轨迹，但四个 P 映射均未确认
- **THEN** 质量产物 SHALL 报告非零感知层计数和零正式身份覆盖
- **AND** verdict SHALL 为 fail，原因包含身份绑定失败

#### Scenario: 四槽占用但只在一端有轨迹

- **WHEN** roster_occupied_count=4 而 metric-eligible 样本长期只覆盖一个 canonical 端位
- **THEN** verdict SHALL 为 fail，原因包含端位覆盖不足
- **AND** 产物 SHALL 指出每个缺失槽位的最早可判断点与 `unresolved_no_slot` 等相关拒绝计数

#### Scenario: 全片末段无球员

- **WHEN** 视频仍有可处理帧而所有球员连续缺失超过配置最长缺口
- **THEN** 质量产物 SHALL 记录起止时间和缺失长度
- **AND** 页面 SHALL 明确显示四人识别质量不足

### Requirement: 本次真实双摄素材的新 Job 验收

对 `ct_9997fa5aedf7` 的修复验收 SHALL 创建新 `joint_tracking_v2` Job，使用该 Job 冻结的四人名册，对照 `job-9a640b069a` 的基线产物。通过条件 SHALL 包括四人唯一确认、Team A/B 各两人位于用户确认的 canonical 端位、每人正式 coverage ≥0.70、最长连续缺失 ≤2.0s、未裁决身份互换/重复绑定/正式跨侧污染均为零；同时检查开场、锚点附近、长缺口及末段的 overlay 和热力图。不得靠改写旧产物或调低当次门槛宣称通过。

#### Scenario: 新任务仍只生成同侧 P2/P3

- **WHEN** 新 Job 的有效轨迹仍只覆盖同一端位或任一确认球员 coverage 未过门槛
- **THEN** 验收 SHALL 失败
- **AND** SHALL 保存按检测、local、global、身份审计分层的差异摘要

#### Scenario: 四人全片通过

- **WHEN** 新 Job 达到全部覆盖、缺口、端位与身份硬门槛
- **THEN** 验收 SHALL 保存新旧 Job ID、配置签名、阈值和结构化对照
- **AND** overlay 与热力图 SHALL 只显示经审计确认的 P 身份
