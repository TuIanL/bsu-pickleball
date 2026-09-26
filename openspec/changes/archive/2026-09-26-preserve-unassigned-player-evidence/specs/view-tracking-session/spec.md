## ADDED Requirements

### Requirement: Joint candidate evidence remains separate from formal identity

在 `joint_tracking_v2` 中，`ViewTrackingSession` SHALL 为未满足 `lock_only` formal eligibility、但仍存活且具有有效场地投影的 track 输出候选证据。候选 SHALL 至少包含 view、source frame、track/tracklet lineage、bbox、脚点、场地坐标和质量；MUST NOT 被标成正式 `Player_N` observation。候选不得影响旧的默认单视角 `step()` 行为。

#### Scenario: 未锁定但可投影的 track 保留为候选
- **WHEN** live track 未进入 formal eligibility 且投影落在有效球场范围内
- **THEN** joint result SHALL 暴露该 track 的候选证据
- **AND** SHALL 保留其来源与质量信息
- **AND** SHALL NOT 将其添加到 `frame_detections` 的正式身份集合

#### Scenario: 场外或投影失败候选不进入恢复
- **WHEN** 候选 track 的场地投影失败或落在 tracking court 范围外
- **THEN** 该 track SHALL NOT 进入 joint candidate recovery input
- **AND** SHALL 可在诊断中记录相应排除原因

#### Scenario: 单视角兼容
- **WHEN** 调用默认单视角 `step()` 或候选策略关闭
- **THEN** 返回的正式 detections、identity 和 metrics SHALL 保持原语义
