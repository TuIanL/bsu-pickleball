## Why

当前球体识别和球路重建主要依赖 detector、连续性、物理门和轨迹拟合，尚未利用“是否正在比赛”这一比赛语义。结果是比分结束、捡球、准备发球等非比赛时刻仍会持续寻找球，容易把手持球或场外物体纳入轨迹；反过来，比赛中的严格质量门又可能误删真实球。当前双摄 v4 还在球员当帧感知之前完成球 detector/tracker 更新，缺少一个统一的语义搜索入口。

第一步先建立比赛语义驱动的球搜索策略，不修改球体识别模型文件，也不立即改变正式球路结果。通过权威时间线、球员运动/站位和发球候选等证据生成语义状态快照，在 Shadow Mode 下记录“应搜索、应抑制、应重新捕获”的策略结果，为后续回合事件仲裁和正式输出切换提供可验证基础。

## What Changes

- 新增比赛语义状态快照，区分 `authority`（人工或修正时间线）与 `evidence`（视觉规则推断），并统一使用 canonical take time。
- 新增球搜索策略状态：`UNKNOWN`、`NON_PLAY_CONFIRMED`、`PRE_SERVE`、`SERVE_ARMED`、`RALLY_ACTIVE`、`RALLY_END_CANDIDATE`、`POST_RALLY`。
- 将权威 `non_play`、`rally_start`、`rally_end` 和有效比赛时间窗口接入球搜索策略；权威非比赛区间可以抑制正式球跟踪，未知或仅由算法推断的状态必须支持 `UNKNOWN` 回退。
- 为球 detector、候选过滤、BallTracker 更新和候选发布定义策略决策，但第一阶段只运行 Shadow Mode，不改变现有正式球轨迹、事件和 v4 分段结果。
- 保留被策略抑制的原始候选及其原因，产出可审计的语义时间线/诊断信息，避免“抑制”与“删除证据”混为一谈。
- 为双摄 canonical 球处理预留 `prepare_tick` → 语义评估 → `commit_tick` 的时序契约，使策略能够消费当 tick 的球员感知与全局身份信息，同时保证每视角每 tick detector 只运行一次、tracker 最多更新一次。
- 将现有 ServeStartDetector 的发球识别结果作为语义证据使用；本阶段只负责进入发球准备/捕获策略，不确认完整击球、回合结束或比分结果。

## Capabilities

### New Capabilities

- `ball-semantic-search-policy`: 根据比赛时间线和多源视觉证据生成比赛语义状态，并决定球搜索、候选过滤、tracker 更新和候选发布策略；支持 Shadow Mode、UNKNOWN 回退和诊断产物。

### Modified Capabilities

- `ball-tracking`: 球跟踪在获得语义搜索策略时，必须区分正式跟踪输出与被策略抑制的原始候选；权威非比赛时间线可抑制正式球跟踪，但缺少或不确定语义时仍保持现有兼容行为。

## Impact

- 主要影响 `backend/app/vision/pickleball_game_analysis/ball_tracker.py`、`backend/app/vision/multiview/ball_stereo/canonical_runner.py`、`backend/app/vision/multiview/multiview_joint_run.py` 和 `backend/app/services/analysis_pipeline.py`。
- 复用现有 `effective_time_windows`、`ServeStartDetector`、`BallTracker.update_from_candidates`、canonical take clock、player tracking/global registry 和时间线事件查询能力。
- 需要新增语义策略配置、Shadow Mode 诊断字段及回放/回归测试；不修改球体识别模型权重，不在本变更中实现正式击球归因、回合结束判定或比分裁决。
- 现有球检测、球路和球员分析在策略不可用、模型不可用或语义状态为 `UNKNOWN` 时继续按兼容路径运行。
