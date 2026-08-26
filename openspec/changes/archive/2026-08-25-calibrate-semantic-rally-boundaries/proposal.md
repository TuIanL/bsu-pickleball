## Why

第二阶段已经能够在权威 `non_play`、`rally_end` 和 `rally_start` 边界封存、重置和重新打开正式球段，但算法证据仍主要停留在软约束，且缺少跨时间窗口的稳定性判断。若直接扩大 Enforced rollout，单次漏球、球员短暂停止或准备动作变化都可能造成过早封存，反过来真实回合结束也可能因为证据不足而让误检跨回合传播，因此现在需要在真实双摄素材上校准回合边界的多证据仲裁逻辑。

## What Changes

- 新增语义证据融合与时间稳定性层，统一记录比分/时间线、球员运动与站位、ServeStartDetector、球候选运动性、场地区域和球路连续性等证据，并区分 `authoritative`、`observed`、`algorithmic` 与 `none` 来源。
- 为 `RALLY_END_CANDIDATE`、`PRE_SERVE` 和 `SERVE_ARMED` 增加时间迟滞、最小持续窗口、证据数量门槛和相互矛盾证据处理，禁止单帧弱证据直接产生正式封存或重新打开 action。
- 增加回合边界仲裁结果：`pending_end`、`confirmed_end`、`pending_start`、`confirmed_start`、`rescued_active` 等可审计状态；当持续出现有效球运动和球员比赛活动时，允许从结束候选中救援当前回合，避免误删真实球路。
- 保持第二阶段的权威硬门原则：只有 manual/corrected 且显式 Enforced rollout 的确认边界才能改变正式 Tracker 生命周期；算法证据可以改变候选状态、优先级和 Shadow 诊断，但不得单独硬关闭正式球链。
- 为每个 canonical tick 记录语义证据快照、候选边界、确认原因、迟滞计数、冲突证据、boundary action 和 formal candidate before/after，生成可重放的语义边界评估 artifact。
- 建立 7 月 20 日真实双摄素材及可复现合成案例的校准集，覆盖捡球/准备、发球预热、正常回合、球丢失、碰网候选、真实回合结束和下一回合重捕获等场景。
- 增加边界质量指标：回合开始/结束 precision、recall、确认延迟、误封存率、跨回合污染率、真实球路误抑制率、重捕获延迟和 detector 调用次数；支持 Shadow 与 Enforced 的逐时间点对照。
- 不修改球体识别模型文件，不把算法边界直接写入比分，不在本阶段实现最终击球者归属、出界裁决或新的评分模型。

## Capabilities

### New Capabilities

- `semantic-rally-boundary-calibration`: 定义语义证据融合、回合边界迟滞/仲裁、可重放评估 artifact、校准案例和边界质量指标。

### Modified Capabilities

- `ball-semantic-search-policy`: 增加多证据稳定性、候选边界、冲突处理、回合救援和确认后 boundary action 的要求。
- `ball-tracking`: 增加 pending boundary、grace window、rescue active 和跨段污染评估要求，继续保持权威硬门与未知状态 fail-open。
- `analysis-artifacts`: 增加语义边界评估 artifact 的版本、存储、状态和 API 读取契约。

## Impact

- 影响 `ball_semantic_search_policy.py`、`analysis_pipeline.py`、`ball_tracker.py`、双摄 `canonical_runner.py` 以及语义时间线/诊断 artifact writer。
- 需要复用现有 canonical take clock、CaptureTake 时间线、ServeStartDetector、球员 global state、BallTracker 连续性状态和双摄 prepare/commit barrier。
- 需要新增语义证据聚合配置、迟滞窗口、边界评估 schema、真实素材回放脚本和回归 fixture；默认继续 Shadow/fail-open，不改变未启用 Enforced rollout 的历史结果。
- 主要验证素材为 2026-07-20 双摄 take；模型权重、detector 调用边界、已有 `ball_trajectory`/`reconstructed_ball_trajectory` 历史 artifact 和评分 FSM 保持兼容。
