## Why

当前系统虽然在分析任务元数据中保存了 `matchFormat: "singles" | "doubles"`，但比赛制式没有传播到分析流水线。球员选择、身份锁定、骨架识别、指标计算和结果展示仍默认按照四名球员运行，导致单打视频可能产生多余球员身份、错误骨架、错误热力图和不适用的双打指标。

## What Changes

- **新增 MatchAnalysisContext** — 后端从 `matchFormat` 统一派生分析上下文，封装总人数、每侧人数、分侧配额、双打间距开关等参数
- **Worker 将上下文传入 Pipeline** — `AnalysisPipeline.run()` 增加 `match_context` 参数，覆盖全局配置中的固定 4 人设置
- **PrimaryPlayerSelector 移入 `_run_tracking`** — 生命周期与 tracking run 一致，`max_subjects` 和 `group_profile` 由赛制动态决定
- **PlayerGroupProfile 替代硬编码双打人数结构** — `_group_consistency_score` 中的 `same_side_expected=1/opposite_expected=2` 改为赛制感知
- **PlayerLockManager 增加分侧配额和统一分配路径** — early lock / finalize bootstrap / late lock 共享同一 `_assign_candidate_to_slot` 方法，强制 near/far side quota
- **PlayerIdentityManager 使用任务级 `max_players`** — 单打不创建 Player_3/Player_4
- **Bootstrap 增加 deadline fallback 机制** — 截止时仍未满足分侧配额时允许受控降级，写入结构化诊断
- **Fallback 身份增加 `fallback_tentative` 状态** — 可被缺失侧的高质量候选替换，不永久锁死错误身份
- **`_is_in_near_court_area` 重命名并澄清语义** — 避免"球场邻域"和"近端半场"两个 near 概念混淆
- **Formal eligibility 链修正** — 移除 `lock_update.eligible_track_ids | suggested_track_ids` 并集，正式输出只消费 LockManager 接纳的 track
- **Selector 增加 quota-aware 最终组合选择** — 排序后按 near/far 配额分组选取，覆盖 rule 和 attention 两条路径
- **`doubles_spacing` 改为赛制感知** — 单打返回 `not_applicable`，双打识别不完整返回 `insufficient_players`；维持现有 List 类型兼容，新增 `metric_statuses` 旁路
- **分析结果携带 match_context** — `observed_player_count` 和 `expected_player_count` 写入 artifact，前端据此动态渲染
- **`MatchAnalysisContext` 只包含领域事实** — `PlayerGroupProfile` 作为内部算法配置，由 `build_player_group_profile(context)` 派生，不持久化
- **统一 `player_analysis_hard_limit`** — 合并三个独立人数上限为一个容量配置，容量不足时明确报 configuration error，不静默 min
- **兼容处理** — 缺失 `matchFormat` 的历史任务默认按双打处理并写入兼容诊断；不保证新版本算法结果与旧版本 bitwise identical

## Capabilities

### New Capabilities
- `match-format-context`: MatchAnalysisContext schema 定义、build_match_context 派生函数、通过 Worker/Pipeline/子组件的传播机制
- `singles-aware-player-selection`: 赛制感知的 PrimaryPlayerSelector（GroupProfile）、PlayerLockManager（分侧配额）、PlayerIdentityManager（动态人数上限）

### Modified Capabilities
- `player-tracking-engine`: 现有 "participant-limited overlay labels" 和 "参与人数限制" 需求需要从"固定配置值"改为"由 MatchAnalysisContext 驱动"
- `match-analysis-pipeline-capabilities`: 新增对赛制感知指标状态（not_applicable / insufficient_players）的需求，以及 match_context 在 pipeline result 中的持久化

## Impact

- **后端**: `backend/app/services/analysis_pipeline.py`（run 签名、_run_tracking、_compute_metrics）、`backend/app/services/job_orchestration.py`（Worker 传入 match_context）、`backend/app/vision/player_tracking_engine/`（primary_player_selector、player_lock_manager、player_identity）
- **API**: 请求结构无破坏性变更（matchFormat 已在前端 Payload 中）；分析结果指标存在非破坏性 schema 扩展（`metric_statuses` 旁路字段）
- **配置**: 三个独立人数配置合并为统一 `player_analysis_hard_limit: int = 4`；旧配置名保留为 deprecated alias，启动时检测冲突
