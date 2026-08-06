# fix-player-identity-reconnect-and-track-fragmentation

## Why

job-6c0cc96f86 在 21-23 秒，P1 因离画面远暂时未被检测到（track 6 丢失），随后身份锁把 P1 错接到 P2 区域的 track 50，小地图 P1 蓝点瞬移到 P2 附近来回抽搐。诊断数据实锤：两次错误重连 `position=0.00`（候选距离 P1 最后确认位置 20.6 米）却因 motion/side/bbox 分数补足而通过 `reconnect_threshold`。更深一层：track 50 本身是跟踪器把 P2 分身出的**重复重叠 track**（与 track 41 的 bbox IoU 0.64-0.68 持续 5+ 帧）——这个"幻影候选"本就不该存在。

## What Changes

- **A. 身份锁重连空间门控**：重连候选距离槽位最后确认位置超过"允许距离"（`max_reconnect_distance_ft` + 估计速度 × 流逝时间）时 **硬性拒绝**，保持 LOST（蓝点冻结在最后可信位置）；同侧但横向错配的候选侧分从 0.75 压到 0.2，无法单独凑够阈值。位置与 `max_reconnect_distance_ft` 单位一致（均为英尺），问题在于距离只作软分数、非位置分量能补足阈值。
- **B. 重复重叠 track 抑制**：球员多目标跟踪输出后增加重复 track 抑制——两个 track 的 bbox IoU ≥ 0.6 持续 ≥ 5 帧时，只输出较新/较低置信度之外的那个，从源头消灭"幻影候选"。
- **BREAKING**：后端行为变化，需要重跑分析任务验证效果。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `player-lock-state-machine`: LOST/LOCKED 槽位重连增加空间距离门控与横向错配惩罚；重连不再接受 position=0 的远距离候选。
- `player-tracking-engine`: 球员跟踪输出新增重复重叠 track 抑制，消除同一目标的重复 track。

## Impact

- `backend/app/vision/player_tracking_engine/player_lock_manager.py` — `_compute_reconnect_score` 加硬距离门（含时间缩放）、`_reconnect_side_score` 横向错配惩罚。
- `backend/app/vision/player_tracking_engine/player_lock_types.py` — 新增重连门控配置项。
- `backend/app/vision/player_tracking_engine/multi_object_tracker.py` — 新增 `DuplicateTrackSuppressor`（或等价实现）。
- `backend/app/services/analysis_pipeline.py` — 球员路径 `tracker.update()` 后接入重复 track 抑制。
- 测试：`test_player_lock_manager.py`、`test_multi_object_tracker.py`（或新增测试文件）。
- 不涉及前端渲染、schema、存储。
