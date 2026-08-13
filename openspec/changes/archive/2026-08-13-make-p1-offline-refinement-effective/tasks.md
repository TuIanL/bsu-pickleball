## 1. F0 Snapshot 与 F1 Contracts

- [x] 1.1 定义 `F0RefinementSnapshot`，按 canonical tick 保存 timestamp、reference frame、per-view source frame/timing/status、original observations、global identity、prediction 和 metric scope；补 schema/序列化测试
- [x] 1.2 定义 `RefinementViewContext`，包含 view-specific frame provider、detector、homography、inverse homography、orientation、frame geometry 和 timing metadata；删除 F1 对 secondary-only 参数的隐式依赖
- [x] 1.3 将 `P1OnlineRecoveryConfig` 的 donor threshold、missing window、residual、safety gate 阈值纳入 refinement config snapshot，并写入 diagnostics
- [x] 1.4 让 F0 在 online run 完成后先原子写出 immutable F0 artifact，再向 F1 传递 snapshot；验证 F1 失败时 F0 仍可独立消费

## 2. Recovery Window 与 Tick Plan

- [x] 2.1 从 F0 snapshot 挖掘双向 `RecoveryWindow`，严格区分 target frame unavailable、target missing/weak/lost 和 donor 不合格
- [x] 2.2 生成不可变 `RecoveryTickPlan`，使用 F0 canonical timestamp/source timing，不再使用 `tick * 1000 / 30` 或 nominal FPS 推导
- [x] 2.3 将 donor 资格改为 per-tick original/base observation，并使用 refinement config 的真实 `min_donor_quality` threshold
- [x] 2.4 修正 forward/backward anchor 选择：before 使用目标 tick 前最近有效 anchor，after 使用目标 tick 后最近有效 anchor；补视频起点/终点/单侧/无侧测试
- [x] 2.5 增加窗口与 plan 的 freeze/immutability 测试，证明 recovered evidence 不会影响后续 donor、global 或 F0 state

## 3. Per-view Offline Recovery

- [x] 3.1 改造 `OfflineRecovery` 接收 target `RefinementViewContext`，支持 Cam1 target/Cam2 donor 和 Cam2 target/Cam1 donor 两条路径
- [x] 3.2 复用 local-space guided pre-gate，确保 bbox、footpoint、projection、orientation、canonical residual 和 motion strict gate 使用 target view geometry
- [x] 3.3 保证 detector 只读取 target source frame，生成 `RecoveredViewObservation`，并保留 canonical timestamp、source timing、donor、expected global、residual 和 `offline_refinement` provenance
- [x] 3.4 让 `RecoveryTracklet` 只在单个 window 内累积，不调用 F0 tracker/lock/identity/global registry；补 accepted/rejected zero-side-effect 测试
- [x] 3.5 增加不同分辨率、不同 orientation、双向 target、错误 geometry 和 source decode failure 的回归测试

## 4. Evidence Freeze 与正式 Re-fusion

- [x] 4.1 实现 original/recovered evidence 的 deterministic merge：original strong 优先、同 global/tick/view 去重、duplicate/suppressed reason 可诊断
- [x] 4.2 新增 F1 refusion adapter，基于 F0 global identity map 将 merged per-view observations 转为既有 canonical observation contract
- [x] 4.3 复用 `view_intrinsic_quality`、`pair_consistency`、`fuse_observation` 和既有 fusion config，重新计算 dual/single/conflict/unavailable 状态
- [x] 4.4 从完整 F0 canonical tick 序列重新执行 temporal filtering，生成 Candidate `fused_player_trajectory.f1.v2.json`，禁止 append recovered FusedSample 或局部补丁
- [x] 4.5 确认 recovered evidence 的 `observation_origin` 贯穿 F1 view observations，且 `fusion_status` 不出现 `offline_refinement`
- [x] 4.6 删除/停用 `refuse_f1()` append-sample 路径，补充“Cam1 missing + Cam2 base → F1 dual”与冲突/原始强观测优先测试

## 5. Metric Eligibility 与 Acceptance Gate

- [x] 5.1 移除 recovered observation 或 F1 sample 的 `metric_eligible=True` 强制赋值，统一交给 fusion/metric eligibility policy
- [x] 5.2 实现 F0/F1 对齐指标计算：eligible coverage、recovered count、original strong preservation、jump violation、speed violation、conflict、residual P50/P90、donor inconsistency
- [x] 5.3 实现可配置 `RefinementAcceptanceGate`：通过发布 F1，拒绝回退 F0 并保留 Candidate F1，异常区分为 `failed_fallback`
- [x] 5.4 将 metrics、thresholds、verdict 和 reject reason 写入 `refinement_diagnostics.json`，补 coverage/jump/speed/conflict/residual 各拒绝分支测试
- [x] 5.5 增加 F0 artifact hash/content immutability、predicted 不进指标、offline origin 不强制 eligible 的回归测试

## 6. Executor、Manifest 与原子发布

- [x] 6.1 改造 `multiview_joint_executor.py`：F0 → snapshot → recovery → evidence freeze → refusion → gate 的顺序固定，`late_fusion_v1` 不进入该路径
- [x] 6.2 以 per-view contexts 调用 F1，移除 reference inverse homography/尺寸对 target view 的 fallback
- [x] 6.3 独立原子写出 F0、recovered、Candidate F1 和 diagnostics，并最后更新 Parent `refinement` manifest
- [x] 6.4 确认四态 manifest、`final_source`、Parent canonical status 和历史 F0-only 读取兼容
- [x] 6.5 补充 executor integration tests：completed、rejected_by_safety_gate、skipped_no_windows、failed_fallback 和中途 artifact write failure

## 7. Regression 与真实验收

- [x] 7.1 运行 F1 synthetic regression：双向恢复、最近 anchor、canonical timestamp、per-view geometry、re-fusion、gate 和 F0 immutability
- [x] 7.2 运行现有 joint/P1-A、timing authority、single-view、`late_fusion_v1` backend regression，确认 P0/P1-A 行为不变
- [x] 7.3 用同一 authoritative 60 秒窗口 `3.4s–60s` 开启 F1，确认不再出现 `visual_acceptance_online_only`
- [x] 7.4 检查 60 秒物理产物：F0、recovered observations、F1、refinement diagnostics；随机抽样 recovered tick 验证 target real pixel → formal re-fusion → F1
- [x] 7.5 60 秒通过后执行约 699 秒全程 run，记录 F1 adoption/rejection/fallback、恢复数量、覆盖率变化、冲突/跳变/速度指标和运行耗时
- [x] 7.6 运行 `openspec validate --all`，保存 acceptance summary，并明确 P1-B 的最终状态与遗留风险
