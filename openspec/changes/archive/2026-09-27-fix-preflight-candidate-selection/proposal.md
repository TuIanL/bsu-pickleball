## Why

预检（player bootstrap preflight）给出的 P1–P4 与真实场上球员不符，导致用户无法核对名册、冻结后的 Team A/B 与下游指标随之失真。真实双摄素材 `take ct_9997fa5aedf7`（174/175 各 587s@60fps）上已复现：4 名真实球员只入选 3 名——近端两名真实球员中的一名（场内占比 1.0、综合分 0.9306、全场第 2）被丢弃，而占位的 P4 是远端同一名球员 1 秒后的重复轨迹（综合分 0.6144、命中 2 帧、无跨机位佐证）。两个直接原因都在预检自身：最终选取用"首帧画面 bbox 中心 x 取最左 4"覆盖了证据排序；短时关联只允许"一条轨迹一帧吸收一个检测"，检测器对同一人给出两个重叠框时无法合并，于是同一人被拆成两条轨迹。

## What Changes

- **BREAKING**（响应内容变化，非接口形状变化）取消"按首帧画面 x 取最左 N"的收尾排序。P1–P4 改为：先按候选证据分排序，再按赛制分侧配额选取（双打 2+2、单打 1+1），槽位按分侧分组稳定编号，使"同一队两人同侧"的球场结构在建议槽位里直接可见。
- 新增同机位**跨帧同人合并**：同一机位的两条轨迹，若在采样时刻上反复互斥出现（同一时刻只有其中一条有观测）且彼此的观测始终落在同一近邻范围内，则判为同一名球员并合并为单一候选，保留最早的观测作为锚点。
- 分侧判据复用正式管线既有语义：canonical 球场坐标 y 中位数 + 2ft 中线死区（对应 `_BootstrapTracklet.inferred_side`），不新造第二套定义。
- 一侧候选不足时**不跨侧补位**：保留该侧已有的可靠候选，写出 `bootstrap_preflight_side_quota_unfilled` 诊断并把状态降级为 `insufficient_candidates`，与既有"不得为了凑满四人选入场外人员""不得用低分隔壁场候选补满"的处理一致。
- 候选证据新增可选的侧向字段（near / far / 未知），供核对、诊断与审计使用；v2 契约既有字段语义不变。

## Capabilities

### New Capabilities

本次不新增能力。选取与同人合并都是既有能力 `automatic-player-roster-candidates` 已经声明的行为（"依据目标球场位置、短时连续性及观测质量产生单打两名或双打四名候选"），本次是把该能力的判定口径改对，而不是引入新能力。

### Modified Capabilities

- `automatic-player-roster-candidates`: 修改"从比赛片段自动选取目标球场球员候选"——四人选取由画面位置排序改为证据排序 + 赛制分侧配额，并把"同一名球员在一次预检内至多产生一个候选""分侧不足时诚实降级而非跨侧补位"写入该 Requirement 的场景。

## Impact

- 后端选取与合并：`backend/app/services/player_bootstrap_preflight.py`（最终选取、跨帧同人合并、新增诊断码与侧向证据）。
- 契约：`backend/app/schemas/rally_context.py` 的 `PlayerBootstrapCandidateEvidence` 增加可选侧向字段（向后兼容，不新增契约大版本）。
- 测试：`backend/tests/test_player_bootstrap_preflight.py`（既有场景数据需给球员分配真实侧向）、`backend/tests/test_player_bootstrap_v2_contract.py`（证据字段与降级路径）。
- 不改动：正式 tracking 管线（`PrimaryPlayerSelector` / `PlayerLockManager`）、预检 API 路由形状、前端组件契约（`AnalysisRosterConfirmation` 只消费 `suggested_slot` 与候选证据，无需改代码；确认页会因选取口径变化而默认呈现不同的槽位映射，这是预期结果）。
- 缓存：`BootstrapPreflightConfig` 新增配置项会进入 `signature()`，因此进程内已有的预检缓存自然失效——预期行为，不需迁移。
