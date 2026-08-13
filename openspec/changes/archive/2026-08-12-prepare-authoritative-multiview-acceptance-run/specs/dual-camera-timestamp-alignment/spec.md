## ADDED Requirements

### Requirement: Manual multi-anchor calibration preparation

系统 SHALL 支持使用至少 3 组、推荐 4-6 组跨越分析时间范围的共同事件锚点，生成 `dual_camera_sync_calibration.v1`。每组锚点 SHALL 使用各 camera 的本地 source time，生成结果 SHALL 保存 reference camera、camera identity、offset、rate、drift、anchor count、residual、quality 和 valid interval。

#### Scenario: 多锚点拟合质量良好
- **WHEN** 锚点覆盖视频前中后段且拟合 residual 在配置阈值内
- **THEN** calibration SHALL 标记 `quality=good`
- **AND** SHALL 保存可复现的拟合参数和 valid interval

#### Scenario: 锚点不足或拟合质量不足
- **WHEN** 锚点少于两个、没有覆盖有效时间范围或 residual 超过阈值
- **THEN** calibration SHALL 标记为 `unknown` 或 `degraded`
- **AND** SHALL 保存 reason
- **AND** SHALL NOT 被宣称为 authoritative good

### Requirement: Automatic timing derivation remains degraded

从 segment `input_start_time` 自动推导的校准 SHALL 保持 `quality=degraded`，即使两路 media 可读且 offset 看似稳定，也 SHALL NOT 绕过人工锚点的 authoritative calibration gate。

#### Scenario: 使用自动推导脚本
- **WHEN** 用户为缺少 calibration 的历史 take 运行自动推导流程
- **THEN** 系统 SHALL 写入结构合法的 `dual_camera_sync_calibration.v1`
- **AND** quality SHALL 为 `degraded`
- **AND** authoritative acceptance SHALL 继续被阻止

### Requirement: Calibration identity and interval validation

加载 calibration 时，系统 SHALL 验证 schema version、reference camera、secondary camera mapping identity、positive rate、finite residual、anchor count、quality 和 valid interval。camera identity 或 interval 不匹配时 SHALL 以结构化 reason 拒绝该 mapping。

#### Scenario: camera identity 不一致
- **WHEN** mapping 的 `camera_id` 或 `reference_camera` 与 joint input 不一致
- **THEN** sync authority SHALL 判定为 unavailable
- **AND** joint run SHALL NOT 声称两路已对齐

#### Scenario: tick 超出 calibration interval
- **WHEN** canonical tick 映射到某路 valid interval 之外
- **THEN** 该 view SHALL 标记 unavailable
- **AND** SHALL NOT 通过 nearest frame 或 offset=0 外推有效观测
