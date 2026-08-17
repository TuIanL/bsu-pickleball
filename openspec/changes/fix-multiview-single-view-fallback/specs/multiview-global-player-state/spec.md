## MODIFIED Requirements

### Requirement: 存在与普通关联资格分离
`GlobalPlayerState` 的"存在于 registry"与"有资格参与普通 association"SHALL 分离：当 `position_uncertainty_ft > threshold` 或 `last_seen_age > threshold`（配置）时，该玩家 SHALL 标记为 stale，退出普通紧门匹配（其预测不作为普通候选吸附观测），仅允许经 historical local continuity、guided recovery、strong reacquire 路径回归；恢复成功后重新获得普通资格。candidate 与从未 confirmed 的 tentative SHALL 可过期淘汰；已进入 roster 的 confirmed global 出画 SHALL 仅降级 weak → lost，等待 recovery，SHALL NOT 删除。仅 roster reset 才销毁。**stale 标记 SHALL 区分"单视图持续活跃"与"跨视图缺失"：玩家存在任一 view binding 且 `last_seen_s` 新鲜（`now_s - last_seen_s <= stale_last_seen_s`）时，SHALL 保持 `association_eligible=True`（豁免仅作用于 last_seen 维度）；`position_uncertainty_ft` 超阈值 SHALL 仍无条件置 stale，不受豁免影响；仅当所有 view binding 均过期（全视图离场）才因 last_seen 维度标记 stale。**

#### Scenario: 候选过期

- **WHEN** candidate 长时间未达晋升条件
- **THEN** registry SHALL 将其过期清理
- **AND** 清理 SHALL 不影响 roster 内 global

#### Scenario: roster 内 P3 出画不删

- **WHEN** roster 内 Global P3 出画（binding 降级 lost）
- **THEN** GlobalPlayerState P3 SHALL 继续存在于 registry
- **AND** 恢复时 SHALL 复用原 global，不得创建新 global

#### Scenario: stale 不吸附

- **WHEN** Global P3 失踪超阈值
- **THEN** P3 的预测 SHALL 退出普通关联
- **AND** 其他观测 SHALL NOT 因 P3 的 stale 预测被误吸附

#### Scenario: 单视图活跃不 stale

- **WHEN** Global P2 仅 cam_1 binding 为 `observed` 且 last_seen 距当前 < `stale_last_seen_s`，cam_2 binding 缺失/过期
- **THEN** P2 SHALL 保持 `association_eligible=True`
- **AND** `predict_all()` SHALL 返回 P2 预测（供关联分配），P2 不因跨视图缺失而结构性丢失

#### Scenario: 明确换场才重建

- **WHEN** 系统识别到 new_match / roster_reset / participant-change
- **THEN** registry SHALL 销毁现有 roster 并重新进入 `BOOTSTRAPPING`
- **AND** 普通遮挡 / epoch reset / 局盘切换 / 换边 SHALL 不触发重建
