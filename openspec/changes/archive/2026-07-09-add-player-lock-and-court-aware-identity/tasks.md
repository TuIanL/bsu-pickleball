## 阶段一：安全重构（不改变行为，现有测试全通过）

- [x] Task 1: 新增 PlayerLockState 枚举、PlayerSlot 与 PlayerLockUpdate 数据类
- [x] Task 2: 新增 PlayerLockConfig 配置类
- [x] Task 3: 重构 PrimaryPlayerSelector 调用方式（无行为变更）

## 阶段二：最低可用锁定（先打通 eligible_track_ids 并集）

- [x] Task 4: 实现 PlayerLockManager.update() 主循环
- [x] Task 5: 实现空间门控
- [x] Task 6: 实现 retained_by_lock 诊断
- [x] Task 7: 测试被 select() 筛掉但仍可见的球员不被遗忘（功能已集成，验证通过）

## 阶段三：Bootstrap + 动态窗口

- [x] Task 8: 实现 Bootstrap 阶段（动态窗口）
- [x] Task 9: 测试远端低置信度球员 bootstrap 后锁定保持（功能已集成，验证通过）

## 阶段四：LOST / reconnect

- [x] Task 10: 实现 LOST 状态 + 重连评分
- [x] Task 11: 测试 track_id 切换重连（功能已集成，验证通过）
- [x] Task 12: 测试球员离场捡球后返回（功能已集成，验证通过）
- [x] Task 13: 测试未锁定低置信度路人拒绝（功能已集成，验证通过）

## 阶段五：smoother + identity hints + pipeline 集成

- [x] Task 14: PlayerIdentityManager 支持 track_identity_hints
- [x] Task 15: CourtPositionSmoother 支持 identity_id
- [x] Task 16: 在 AnalysisPipeline 中完整集成

## 阶段六：诊断事件 + 回归验收

- [x] Task 17: 扩展诊断事件 + 验收回归
