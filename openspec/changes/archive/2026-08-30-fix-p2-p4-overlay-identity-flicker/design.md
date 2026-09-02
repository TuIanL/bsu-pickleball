## Context

任务 `job-43e7475fd8` 的 7–13 秒是当前链路的典型失稳窗口：参考视角中的 P2 观测频繁缺失，fused overlay 在 `REAL_BOX`、`PROJECTED_BOX` 和 `PROJECTED_POINT` 之间切换；同时 `cam_2` 的 local `Player_2`/`Player_4` 观测被重新绑定到不同 global player。现有实现已经具备关联迟滞、槽位唯一性、投影碰撞门和展示状态机，但这些机制分别观察单 tick 或单层状态，尚未把 local slot 的时序稳定性、跨层风险和显示几何一致性连成一个安全闭环。

约束如下：canonical `Player_1..Player_4` 是用户可见身份，roster 确认后不能因单路 local label 变化而重排；`cross_view_projected` 只能补充展示，不能创造检测或身份；旧 artifact/API 需要继续可读；本 change 不修改球检测、球路、姿态或视频同步算法。

## Goals / Non-Goals

**Goals:**

- 在 local track fragment、短时漏检、交叉跑位和双摄冲突时保持 `tracklet → local slot → global → canonical` 的可解释一对一关系。
- 阻止未经充分证据的 P2/P4 跨视角 reassociation，并将不确定样本隔离为 `ambiguous`/`unresolved`。
- 让投影框的 bbox、脚点和可信球员框保持空间一致；碰撞或几何跳变时安全降级，不显示误导性旧框。
- 限制短时间内 box/point/hidden 的往返切换，同时保持真实检测恢复立即升级和 evidence provenance 诚实。
- 通过逐 tick 诊断与同一真实任务的 7–13 秒回归证明修复有效。

**Non-Goals:**

- 不训练或引入新的 detector、ReID 模型或第三方 tracker。
- 不把 appearance 强行用于本场决策；服装不具区分度时仍允许其保持 shadow/zero-weight。
- 不改变 `Player_1..Player_4` 的公开命名、历史 artifact 的读取兼容性或球场坐标契约。
- 不通过前端重新推断身份来掩盖后端 association 错误。

## Decisions

### 1. 将 local slot reassociation 作为独立风险处理

保留现有 global association 的 canonical 几何匹配和一对一匹配，但把 local slot 的历史绑定、tracklet lineage、identity epoch、side/quadrant、运动连续性和当前 incumbent 状态纳入 reassociation gate。`view_player_id` 仍可作为观测标签，但不能单独证明它在 track fragment 或标签抖动后仍代表同一物理球员。

候选接管必须通过连续 tick、预测距离、side/quadrant、唯一槽位、challenger margin 和无冲突检查；候选在窗口内变化、同一 local slot 被多个 global 竞争、或 donor/target 几何不一致时，保持 incumbent 或输出 unresolved。只有最终确认的受控切换才能释放旧槽位，并记录 old/new binding、证据窗口和原因。

替代方案是单纯提高 `reassociation_frames` 或降低 association gate。前者会延长错误绑定，后者会增加吸附和跨侧污染；二者都不能解决 local label 与 track fragment 的语义不稳定，因此不采用。

### 2. 把跨视角冲突样本从正式身份链路隔离

同一 canonical tick 的多视角观测先经过 identity/slot gate，再进入 fusion。若同一 global 的两路观测距离冲突，沿用 prediction-aware 仲裁，但当仲裁同时伴随 local slot reassociation、reference slot conflict 或 ambiguous 状态时，不得用该样本反向重置 roster、reanchor 其他球员或写入正式 canonical 轨迹。保留冲突双方及选路原因供 diagnostics 使用。

替代方案是始终按置信度加权平均。当前窗口已出现明显的跨视角距离冲突，简单平均会把错误位置带入预测并放大下一 tick 的 association 错误，因此不采用。

### 3. 投影框必须同时通过碰撞和 bbox/脚点一致性

`cross_view_projected` 只生成当前 reference view 的 projected footpoint。只有候选 bbox 与当前脚点一致、没有超过可信球员框的 IoU 门、没有超过脚点速度/尺度连续性门时才可进入 `PROJECTED_BOX`。碰撞或几何跳变时，优先使用与当前脚点一致的 point；如果只能复用上一份 presentation geometry，则还必须通过与当前脚点和可信框的二次校验，否则降级为 `PROJECTED_POINT` 或 `HIDDEN`。

真实 bbox 恢复仍立即使用 `REAL_BOX`/`ASSISTED_BOX`；投影和 hold 只能改变展示几何，不能改变 evidence_type、canonical identity 或 bbox memory owner。投影生成的 bbox 不回写真实 bbox memory/scale profile。

替代方案是无条件保留上一份 bbox 以消除闪烁。该策略在 11 秒附近会产生“P2 脚点靠近 P4、框仍停在旧位置”的误导画面，因此不采用。

### 4. 对展示拓扑增加短窗防抖，而非无限平滑

保留现有基于真实时间的状态机和 synthetic upgrade confirmation：真实观测立即升级，synthetic box 需要连续确认，硬 TTL 仍负责最终隐藏。新增短窗拓扑防抖规则：连续无效的投影候选固定在安全 point/hidden 状态，不能在相邻 tick 中反复 box→point→box；每次降级和恢复都记录 transition reason。几何位置仍允许在真实运动门内更新，避免为了防闪烁锁死合法快速移动。

替代方案是把所有 frame 在前端做视觉插值。前端没有身份、碰撞和 evidence authority，且插值会掩盖后端错误，因此不采用。

### 5. 诊断和回归以同一真实任务为验收对象

扩展 display diagnostics 记录 local slot rebind、旧/新 global、reassociation 窗口、projection rejection、bbox/footpoint residual 和短窗 display transition；这些字段 additive 且旧产物缺失时使用兼容默认值。质量产物新增按 view-slot 和 canonical player 的窗口统计。

回归重新运行同一录制任务，并重点检查 7–13 秒：P2/P4 canonical 标签不交换；同一 local slot 不在无连续强证据时换 global；P2/P4 框与脚点无显著脱离；projection collision 不发布误导性框；display topology 不发生高频往返；ambiguous/unresolved 样本不进入正式轨迹。

## Risks / Trade-offs

- [严格 gate 可能暂时不显示真实但难以判定的球员] → 宁可显示 point/hidden 并记录原因，也不把错误球员框写入正式身份链；通过 coverage 和最长缺口监控召回损失。
- [local slot 不稳定会降低 reassociation 成功率] → 保留 tracklet lineage、运动/side 先验和受控 recovery；不依赖单一 raw track id。
- [展示防抖可能滞后真实移动] → 所有时间门基于 source timestamp，真实 bbox 立即升级，合法运动通过速度/尺度门即可更新。
- [新增逐 tick 字段增大 artifact] → 只记录 transition/rebind 事件与必要摘要，保留窗口查询和旧产物兼容，不复制 debug trace。
- [旧任务没有新增诊断字段] → API 读取按字段缺失使用默认值，质量验收只对重新运行的新 Job 生效。

## Migration Plan

1. 先补充 association、overlay state、bbox/footpoint consistency 和 diagnostics 的单元测试及真实片段断言。
2. 在 joint run 中以 additive 字段记录 local rebind 和显示拓扑事件，先生成 shadow diagnostics，不改变旧 artifact。
3. 启用严格 reassociation 与投影安全降级，重新运行 `job-43e7475fd8` 对应素材生成新 Job，并与现有结果对照。
4. 新 Job 通过四人硬不变量、P2/P4 7–13 秒窗口和正式轨迹污染检查后，作为默认 joint overlay 行为。
5. 若出现召回退化，保留旧配置开关用于回滚，但不得回滚诊断和回归门。

## Open Questions

- 7–13 秒窗口最终允许的 display topology transition 次数和 P2/P4 bbox/脚点 residual 阈值，需要由新 Job 与人工抽帧标注共同校准，并写入配置快照。
- local slot lineage 是否直接复用现有 `identity_epoch`，还是新增独立 tracklet lineage id，需要在实现阶段根据 `PlayerLockManager` 的现有生命周期确认。
- 若严格隔离后 P2 coverage 仍低于验收门，应优先扩大受限 ROI recovery，还是补充人工标注/外观特征，需要以新 Job 的断点统计决定。
