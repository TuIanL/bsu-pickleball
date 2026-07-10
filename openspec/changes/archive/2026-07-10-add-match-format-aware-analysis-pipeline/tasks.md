## 1. 建立 MatchAnalysisContext

- [x] 1.1 新增 `MatchFormat` 类型（`Literal["singles", "doubles"]`）
- [x] 1.2 新增 `MatchAnalysisContext` schema（Pydantic BaseModel，含 schema_version，不包含 group_profile）
- [x] 1.3 新增 `PlayerGroupProfile` 与 `build_player_group_profile(context)` 派生函数
- [x] 1.4 实现 `build_match_context(match_format)` 主派生函数，包含完整的 singles/doubles 映射
- [x] 1.5 实现 `_count_match_score(actual, expected)` 偏差匹配分函数
- [x] 1.6 缺失 matchFormat（历史任务 None）返回 doubles 并写入 `match_format_defaulted` 兼容诊断
- [x] 1.7 非法 matchFormat（如 `"single"`）让 API schema 校验返回 422，不静默兜底
- [x] 1.8 确保输入签名计算包含 `matchFormat`（已有 metadata 完整性故仅验证）

## 2. 打通任务到 Pipeline 的传播

- [x] 2.1 `AnalysisPipeline.run()` 增加 `match_context: MatchAnalysisContext | None = None` 参数
- [x] 2.2 Worker `_execute()` 从 `job.metadata.matchFormat` 构造 `MatchAnalysisContext`
- [x] 2.3 Worker `run_kwargs` 中传入 `match_context`
- [x] 2.4 `AnalysisPipeline.run()` 将 `match_context` 传给 `_run_tracking()`
- [x] 2.5 `AnalysisPipeline.run()` 将 `match_context` 传给 `_compute_metrics()`
- [x] 2.6 确保旧调用方不传 `match_context` 时自动 fallback 为 doubles 默认值

## 3. 改造球员识别链路

- [x] 3.1 将 `PrimaryPlayerSelector` 创建从 `AnalysisPipeline.__init__` 移至 `_run_tracking()`
- [x] 3.2 单打使用 `max_subjects=2`，双打使用 `max_subjects=4`
- [x] 3.3 PrimaryPlayerSelector 新增 `group_profile` 参数替代硬编码分组权重
- [x] 3.4 `_group_consistency_scores()` 改为使用 `PlayerGroupProfile` 和 `_count_match_score()`
- [x] 3.5 单打 `group_profile` 配置 `expected_same_side_others=0, expected_opposite_players=1`
- [x] 3.6 双打 `group_profile` 配置 `expected_same_side_others=1, expected_opposite_players=2`
- [x] 3.7 `PlayerLockManager` 在 `_run_tracking` 中使用 `match_context.expected_player_count` 创建
- [x] 3.8 `PlayerIdentityManager` 在 `_run_tracking` 中使用 `match_context.expected_player_count` 创建
- [x] 3.9 移除 formal eligibility 中 `lock_update.eligible_track_ids | suggested_track_ids` 的并集逻辑
- [x] 3.10 Selector suggestions 仅作为 LockManager 输入和诊断信息，不进入 formal eligibility
- [x] 3.11 正式框、骨架、身份、轨迹只消费 `lock_update.eligible_track_ids`
- [x] 3.12 PrimaryPlayerSelector 末尾增加 `_select_balanced_candidates()`，按 near/far 配额分组选取
- [x] 3.13 `_select_balanced_candidates()` 必须覆盖 rule 和 attention 两条选择路径
- [x] 3.14 统一三个独立人数配置为 `player_analysis_hard_limit`
- [x] 3.15 旧配置名保留为 deprecated alias，启动时检测冲突
- [x] 3.16 容量低于比赛需求时抛 `PipelineConfigurationError`（不静默 min）

## 4. 改造 Bootstrap 与分侧逻辑

- [x] 4.1 重命名 `_is_in_near_court_area` 为 `_is_in_court_neighborhood`
- [x] 4.2 `PlayerLockConfig` 新增 `near_side_quota`、`far_side_quota`、`allow_quota_fallback` 字段
- [x] 4.3 `_BootstrapTracklet` 新增 `inferred_side(half_length)` 方法（使用中位数，含 dead zone）
- [x] 4.4 创建统一 `_assign_candidate_to_slot()` 方法：检查 side quota、设置 assignment_side
- [x] 4.5 改造 `_try_early_lock()` 使用统一分配方法
- [x] 4.6 改造 `_finalize_bootstrap()` 使用统一分配方法（按 side 分组后分配）
- [x] 4.7 改造后 bootstrap 阶段 `_try_lock_slot()` 使用统一分配方法
- [x] 4.8 `PlayerSlot` 新增 `assignment_side` 字段（首次分配半场，不随移动更新）
- [x] 4.9 Side occupancy 从 slot 状态派生而非维护可变计数器
- [x] 4.10 新增 `fallback_tentative` slot 状态
- [x] 4.11 实现 bootstrap deadline fallback 机制（截止后允许受控降级）
- [x] 4.12 降级触发时写入结构化 `side_quota_fallback` diagnostic（通过 _assign_candidate_to_slot）
- [x] 4.13 实现 fallback_tentative 替换逻辑（条件：正确侧 + 置信度超过原候选项）
- [x] 4.14 实现 fallback_tentative promotion（持续超过 `fallback_promotion_frames` 后转 `tentative`）
- [x] 4.15 替换时记录 `side_quota_fallback_replaced` diagnostic
- [x] 4.16 确保 late lock（bootstrap 后）仍然设置 `assignment_side`

## 5. 改造指标与可视化

- [x] 5.1 `PerformanceMetrics` 新增 `metric_statuses: dict[str, MetricStatus]` 旁路字段
- [x] 5.2 `_compute_metrics()` 接收 `match_context`，根据 `enable_doubles_spacing` 填充 `metric_statuses["doubles_spacing"]`
- [x] 5.3 `doubles_spacing: List[DoublesSpacingSummary]` 保持 List 类型不变（单打为空数组）
- [x] 5.4 单打时 `metric_statuses["doubles_spacing"]` = `{"status": "not_applicable", "reason": "singles_match"}`
- [x] 5.5 双打识别不完整时 `metric_statuses["doubles_spacing"]` = `{"status": "insufficient_players", ...}`
- [x] 5.6 更新前端 `AnalysisPipelineResult.metrics` 类型定义增加 `metric_statuses`
- [x] 5.7 `PlayerTrajectoryArtifact` 增加 `match_context` 和 `observed_player_count` 字段
- [x] 5.8 `AnalysisPipelineResult` 增加 `match_context` 和 `observed_player_count`
- [x] 5.9 小地图根据实际 `player_ids` 动态生成图例（不硬编码 4 人，已有实现基于实际 `players` keys）
- [x] 5.10 热力图只针对实际 roster 生成个人图（不生成 Player_3/4 空白图，已有实现基于实际轨迹 keys）

## 6. 前端改造

- [x] 6.1 上传页"比赛形式"选择器从 `<select>` 改为分段按钮（视觉更突出）
- [x] 6.2 从 `FieldSession` 或 `RecordingSession` 进入时自动预填 matchFormat（已有实现）
- [x] 6.3 任务详情和报告页显示比赛制式标识（已有实现，通过 metadata.matchFormat）
- [x] 6.4 报告页根据 `metric_statuses.doubles_spacing?.status === "not_applicable"` 隐藏双打专属模块
- [x] 6.5 报告页根据 `observed_player_count !== match_context.expected_player_count` 展示识别覆盖告警

## 7. 测试

- [x] 7.1 `build_match_context` 单元测试（singles/doubles/None/unknown）
- [x] 7.2 `_count_match_score` 单元测试（匹配、偏差、极端值）
- [x] 7.3 单打画面 2 球员 + 2 路人：选择器选出 A+C，不选 A+B
- [x] 7.4 单打前 60 帧只有近端候选，远端第 90 帧出现：early lock 不提前占满 near slot
- [x] 7.5 远端球员直到 bootstrap_max_frames 后不可见：触发 fallback，产生 diagnostic
- [x] 7.6 通过 `_try_early_lock` 锁定：`assignment_side` 非空
- [x] 7.7 通过 `_try_lock_slot` 后期锁定：`assignment_side` 非空
- [x] 7.8 单打完美分组：same_side_others=0, opposite=1 → group_score 满分
- [x] 7.9 双打完美分组：same_side_others=1, opposite=2 → group_score 满分
- [x] 7.10 单打同侧出现路人：same-side composition 得分下降
- [x] 7.11 单打 `doubles_spacing` 返回 `not_applicable`
- [x] 7.12 双打识别不完整返回 `insufficient_players`
- [x] 7.13 同视频 singles/doubles 不同提交产生不同任务签名
- [x] 7.14 旧版本调用不传 match_context 不崩溃
- [x] 7.15 Selector 建议两名近端，但 LockManager 只接受一名：formal eligible 不得通过并集重新包含第二名
- [x] 7.16 Attention 返回两名同侧球员：quota-aware final selection 仍应选择一近一远
- [x] 7.17 Fallback 分配同侧路人后，缺失侧正式球员出现：fallback_tentative 可被替换，已 locked 的 slot 不被抢占
- [x] 7.18 Slot reset/reassign 后 side occupancy 正确释放
- [x] 7.19 doubles + hard_limit=2：任务明确失败为 configuration_error，不伪装成 player_count_mismatch
- [x] 7.20 新请求 matchFormat="single"：返回 422；历史任务缺失 matchFormat：默认 doubles + compatibility diagnostic
- [x] 7.21 metric artifact 兼容：旧前端读取新结果时 doubles_spacing 为合法空数组不崩溃
- [x] 7.22 单打正式输出：tracking overlay、pose、trajectory、minimap、heatmap 均不出现未经 LockManager 接纳的 suggested track
