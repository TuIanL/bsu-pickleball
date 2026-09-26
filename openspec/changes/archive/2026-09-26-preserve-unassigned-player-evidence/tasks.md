## 1. 候选证据采集

- [x] 1.1 扩展 joint `ViewFrameResult` 候选记录，使每个候选携带对应 position、投影状态、tracklet lineage 与质量，且不进入正式 `frame_detections`
- [x] 1.2 在 joint run 中单独收集各 view 的候选观测，并将它们与正式 `JointObservation` 分开传入 association

## 2. 有界恢复与安全关联

- [x] 2.1 为 `GlobalPlayerAssociator` 增加按 view/tracklet 聚合并按 TTL 清理的候选证据状态
- [x] 2.2 实现稳定度、canonical geometry、uncertainty gate、次优 margin、一对一和槽位冲突门控；候选只恢复已有 roster global
- [x] 2.3 将正式 unmatched observation 保留为可恢复证据，并区分 pending、ambiguous、recovered、expired 与 rejected

## 3. 名册与质量产物

- [x] 3.1 保证候选恢复不会建立新 global 或确认 synthetic canonical mapping；后续正式 reference binding 可确定公开身份
- [x] 3.2 将候选恢复漏斗、有效阈值、P1–P4 anchor confirmation 与缺失原因写入四人识别质量产物

## 4. 集成检查

- [x] 4.1 检查结果 composer、trajectory 与报告只消费通过 association 的 recovered observations，不消费 pending/ambiguous 候选
- [x] 4.2 检查已有工作树改动与本次变更的差异，确保保留预存改动及历史 artifact 兼容性
