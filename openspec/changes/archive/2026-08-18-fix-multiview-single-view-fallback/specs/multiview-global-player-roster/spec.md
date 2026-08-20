## MODIFIED Requirements

### Requirement: confirmed roster 不参与普通 GC，但存在与关联资格分离

candidate 与从未 confirmed 的 tentative SHALL 可过期淘汰；已进入 roster 的 confirmed global 出画 SHALL 只降级 weak → lost 并等待 recovery，SHALL NOT 被删除。仅 roster reset 才销毁。同时，`GlobalPlayerState` 的"存在于 registry"与"有资格参与普通 association"SHALL 分离：当 `position_uncertainty_ft > threshold` 或 `last_seen_age > threshold`（配置）时，该玩家 SHALL 退出普通紧门匹配，仅允许经 historical local continuity / guided recovery / strong reacquire 路径回归。**stale 判定 SHALL 区分"单视图持续活跃"与"跨视图缺失"：若玩家存在任一 view binding 且 `last_seen_s` 新鲜（`now_s - last_seen_s <= stale_last_seen_s`），则该玩家 SHALL 保持普通关联资格，即使其他 view binding 缺失/过期——豁免仅作用于 last_seen 维度，`position_uncertainty_ft` 超阈值仍无条件置 stale；仅全视图离场（所有 binding 过期）才因 last_seen 维度触发 stale。**

#### Scenario: P3 出画不删

- **WHEN** roster 内 Global P3 长时间不可见
- **THEN** GlobalPlayerState P3 SHALL 继续存在（lifecycle=lost）
- **AND** P3 重新出现时 SHALL 恢复为原 global，而非创建新 global

#### Scenario: stale 玩家不参与普通匹配

- **WHEN** Global P3 失踪超过阈值（uncertainty / last_seen_age 超限）
- **THEN** P3 SHALL 退出普通紧门匹配，不吸附其他玩家观测
- **AND** 仅经 historical continuity / guided recovery / strong reacquire 路径回归

#### Scenario: 单视图活跃玩家保持关联资格

- **WHEN** Global P2 仅 cam_1 binding 为 `observed` 且 last_seen 距当前 < `stale_last_seen_s`，cam_2 binding 缺失/过期
- **THEN** P2 SHALL 保持 `association_eligible=True`
- **AND** P2 的预测 SHALL 参与普通关联，cam_1 观测 SHALL 可分配给它（而非全部落入 unresolved）
