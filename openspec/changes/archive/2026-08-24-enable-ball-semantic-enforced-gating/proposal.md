## Why

第一阶段已经在 7 月 20 日真实双摄素材上证明：语义状态、权威时间线、Shadow decision 和 `ball_semantic_timeline.v1` 可以稳定产生，但这些结果默认仍不改变正式球路。因而回合结束后的候选仍可能进入正式 tracker，上一回合的 tracker 状态也可能跨越捡球/准备阶段影响下一分。现在需要把已验证的权威语义安全地接入正式球链，先解决“什么时候应该停止发布”和“什么时候应该重新开始捕捉”这两个边界问题。

## What Changes

- 为单摄和双摄增加按 take 配置的 Enforced rollout；仅对 manual/corrected 权威时间线启用正式硬门，默认全局仍保持 Shadow，支持一键回滚。
- 在 `NON_PLAY_CONFIRMED`、`POST_RALLY` 和权威 `rally_end` 区间禁止新候选进入正式 tracker/轨迹发布，同时保留 raw candidate、抑制原因和语义诊断。
- 明确 tracker 生命周期：确认回合结束时封存当前回合的正式球段、清理跨回合预测/候选状态，避免捡球阶段污染下一分；不得把被语义抑制的候选计入静止误检黑名单。
- 在权威 `rally_start`、`PRE_SERVE`、`SERVE_ARMED` 阶段实现渐进式重新捕获：允许发球区域候选进入预热/捕获路径，但不能仅凭手持静止球产生正式球点。
- 将 semantic boundary action、正式发布前后候选计数、tracker reset/preserve 行为和 fallback 原因写入 `ball_semantic_timeline.v1` 或等价诊断，支持新旧策略对照回放。
- 对 7 月 20 日双摄真实球场素材执行同一时间点的 Shadow-vs-Enforced 对照，重点核对非比赛抑制、发球重新捕获、回合边界封存、单视角短时丢失和未知上下文回退。
- 不修改球体识别模型文件，不在本阶段实现击球者最终归属、出界裁决或比分裁决；算法推断的非比赛状态继续保持软约束/Shadow。

## Capabilities

### New Capabilities

本阶段不新增独立 capability，直接把第一阶段的语义搜索策略推进到受控正式门控。

### Modified Capabilities

- `ball-semantic-search-policy`: 增加权威语义到正式 gate、回合边界 action、tracker 生命周期和 Enforced rollout 的要求。
- `ball-tracking`: 增加语义门控下的候选消费、回合段封存、跨回合状态清理、发球预热捕获和 fail-open 兼容要求。

## Impact

- 影响 `backend/app/vision/pickleball_game_analysis/ball_semantic_search_policy.py`、`ball_tracker.py`、单摄 `AnalysisPipeline`、双摄 `CanonicalBallStereoProcessor` 与 `MultiViewJointRun` 的候选消费和生命周期编排。
- 影响 `ball_semantic_timeline`、`ball_trajectory`、双摄 v3/v4 轨迹 diagnostics 的 boundary metadata、suppression counters 和 rollout 配置快照。
- 需要新增或补充配置、单元/集成/真实素材回放测试；现有球 detector、模型权重、球员识别与旧兼容路径保持不变。
