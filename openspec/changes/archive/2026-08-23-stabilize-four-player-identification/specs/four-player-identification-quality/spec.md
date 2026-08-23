## ADDED Requirements

### Requirement: 四人识别质量产物
系统 SHALL 为真实双打 Job 生成 `four-player-identification-quality.v1`，记录配置阈值、attempted tick 数以及 P1-P4 的 detection/canonical coverage、最长缺口、source track history、reconnect、identity switch、duplicate binding、cross-side、ambiguous 与 quarantined sample 计数。

#### Scenario: 完成双打任务生成逐人摘要
- **WHEN** 真实 doubles Job 完成球员身份分析
- **THEN** 质量产物 SHALL 为 P1-P4 各生成一项结构化摘要
- **AND** SHALL 记录本次运行实际使用的阈值和算法版本

#### Scenario: 旧任务没有质量产物
- **WHEN** 查询未生成该产物的历史 Job
- **THEN** API SHALL 返回结构化 `unavailable`
- **AND** SHALL NOT 伪造通过状态

### Requirement: 四人识别硬不变量
双打正式结果 SHALL 满足同 tick track↔local slot↔global↔canonical 双射；duplicate binding、一个 source track 同时对应多个 P 槽位、一个 P 槽位同时对应多个 active track、正式 cross-side contamination 均 SHALL 为零。

#### Scenario: 同一检测竞争 P1 和 P2
- **WHEN** 同一 tick 的 source track 同时成为 P1 与 P2 候选
- **THEN** 系统 SHALL 至多接受一个绑定
- **AND** 另一项 SHALL 标记 ambiguous/duplicate 并进入隔离诊断

### Requirement: 覆盖与缺口验收
默认验收配置 SHALL 要求 confirmed roster count=4、每名 canonical player coverage≥0.70、每名最长连续缺失≤2.0s、未裁决 identity switch=0；阈值 MAY 经真实 baseline 评审调整，但 MUST 写入配置与产物且不得在同一次验收中静默降低。

#### Scenario: P2 长期缺失
- **WHEN** P2 canonical coverage 低于配置阈值或最长缺口超过阈值
- **THEN** 任务质量 SHALL 标记失败或不足
- **AND** SHALL 给出 detection、tracking、slot、association 中的主要断点计数

### Requirement: 新 Job 真实回归
真实回归 SHALL 创建新 analysis Job 并保存 baseline/new 的结构化对照；刷新旧 artifact SHALL NOT 视为算法回归。固定验收片段 SHALL 覆盖约第 2 秒 P2 可见性、第 4 秒 P2 不误投到 P1，以及 P2 正式轨迹不进入 P3/P4 对侧区域。

#### Scenario: 新任务改善 P2
- **WHEN** 对同一素材运行变更前 baseline 与变更后新 Job
- **THEN** 新 Job SHALL 满足全部硬不变量
- **AND** minimum per-player coverage、P2 coverage 与 P2 longest gap SHALL 不劣于 baseline

### Requirement: Appearance 贡献与消融可验证
质量产物 SHALL 记录每名球员的 descriptor availability/quality、template update/freeze、appearance weight、参与裁决次数、支持/冲突次数、camera profile confidence 和 non-discriminative fallback。验收 SHALL 对 appearance disabled/enabled 做消融，确认硬不变量不退化且目标交叉/恢复片段得到改善或保持。

#### Scenario: Appearance 启用后没有正贡献
- **WHEN** enabled 相比 disabled 未改善目标 identity recovery，或增加 identity switch/duplicate/cross-side 任一硬错误
- **THEN** appearance verdict SHALL 标记 no_gain/failed
- **AND** 默认权重 SHALL 保持禁用，不能仅凭特征已实现宣称通过
