## 动机

当前球员追踪流水线存在一个结构性瓶颈：

```
PersonDetector → MultiObjectTracker → PlayerProjector → PrimaryPlayerSelector → PlayerIdentityManager
                                                                      │
                                                          每帧独立打分取 top 4
                                                          远端球员置信度/面积不达标
                                                          即被筛出 eligible_track_ids
                                                                      │
                                                                      ▼
                                                      PlayerIdentityManager 永远看不到
                                                      已被筛掉的球员 → 丢失身份绑点
```

`PrimaryPlayerSelector.select()` 每帧独立运行（`primary_player_selector.py:171`），没有状态保持。远端球员因 bbox 面积小、检测置信度低、投影坐标不稳定，容易掉出 top 4。一旦掉出，`identity_manager.update()` 的 `eligible_track_ids` 参数即将其排除（`player_identity.py:120`），即使该球员仍被 YOLO 检测到。

这与之前球跟踪的 `add-ball-track-lock-and-physics-gating` 是同一种模式：**缺少锁定机制导致短时波动破坏长期身份**。区别在于球是 1 个目标，球员是 4 个目标，且球员有“即使离场捡球也要保持绑定”的更强持久性需求。

## 目标

为双打/单打视频中的主球员建立稳定身份锁定机制，使：

1. 远端低置信度球员（已锁定后）不会被系统遗忘
2. 球员短时离场捡球后返回时保持同一 `player_x` 身份
3. `track_id` 因跟踪器断连而变化时仍能重连到原身份
4. 未锁定的路人/观众/邻场球员不会误入 `player_1~player_4`

## 非目标

- 不替换 `MultiObjectTracker` 或 `PersonDetector`（检测与跟踪层不变）
- 不修改 `PersonDetector` 的置信度阈值
- 不引入 ReID 深度学习模型（首版使用轻量外观特征：框形状 + 颜色直方图）
- 不修改 `trajectory_cleaner`、`bounce_detector`、`court_adapter`
- 不修改 artifact 写入路径与前端接口

## 核心改动

1. 新增 `PlayerLockManager`，位置在 `PrimaryPlayerSelector` 与 `PlayerIdentityManager` 之间
2. `PrimaryPlayerSelector` 从硬门控降级为候选排序器
3. 新增球员锁定状态机：SEARCHING → TENTATIVE → LOCKED → LOST
4. 引入动态 bootstrap 窗口（min 60 / max 180 帧）初始化主球员
5. 新增 `PlayerLockUpdate` 结构，输出 `eligible_track_ids` + `track_identity_hints`（取代类型不一致的 "identity_id 与 track_id 直接并集"）
6. `PlayerIdentityManager` 新增 `track_identity_hints` 参数，支持 lock manager 的身份绑定提示
7. `CourtPositionSmoother` 支持按 `identity_id`（而非 `track_id`）平滑
8. 新增 court-aware 三层空间门控：`inside_court` / `near_court` / `tracking_area`
9. 支持 `target_player_count` 配置（单打=2，双打=4）

## 影响范围

| 文件 | 改动类型 |
|------|---------|
| `player_tracking_engine/player_lock_manager.py` | 新增 |
| `player_tracking_engine/player_identity.py` | 修改（新增 `locked_identity_ids` 参数、扩展诊断事件） |
| `player_tracking_engine/primary_player_selector.py` | 修改（新增 `suggest` 模式、与其他调用方解耦） |
| `player_tracking_engine/court_position_smoother.py` | 修改（支持 `identity_id` 主键） |
| `services/analysis_pipeline.py` | 修改（集成 `PlayerLockManager`、调整 `eligible_track_ids` 逻辑） |
| `core/config.py` | 修改（新增锁定期阈值配置项） |
| `schemas/tracking.py` | 修改（扩展 `PlayerIdentityDiagnostic` 事件类型、新增 `PlayerLockState` 枚举） |
