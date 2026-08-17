## 1. ViewBinding 可用性维度记账

- [x] 1.1 `backend/app/vision/multiview/global_state.py`：`ViewBinding` 新增 `consecutive_available_misses: int = 0`、`last_attempted_take_timestamp_ms: float | None = None`、`last_attempted_tick: int | None = None`、`last_observed_tick: int | None = None`（不触碰既有字段与 `visibility` 语义）
- [x] 1.2 新增幂等记账方法 `record_attempt(result: bool, take_ms: float, tick: int)`：`tick == last_attempted_tick` 时直接 return；有观测（result=True）→ 清零 + 更新 `last_observed_tick`；available miss（result=False）→ 递增 + 更新 `last_attempted_tick` / `last_attempted_take_timestamp_ms`
- [x] 1.3 `backend/app/vision/multiview/recovery_config.py`：`P1OnlineRecoveryConfig` 新增 `fast_recovery_enabled: bool = True`，snapshot() 透出；新增共享纯函数 `is_target_recovery_eligible(binding, fast_recovery_enabled) -> bool`（visibility age OR fast path），供 run 与 guidance 共同 import（MUST NOT 两处各自实现）

## 2. Association 后记账接入（attempt authority）

- [x] 2.1 `backend/app/vision/multiview/multiview_joint_run.py`：在 `process_tick`（L400）之后按 **attempt authority = `view_results`** 记账：`view_id ∈ view_results` 且 `frame_status[view]=="available"` 才记账；有 `AssociationUpdate(global_id, view_id)` → record_attempt(True)；无 → record_attempt(False)；view_degraded / decode 失败（`view_results` 无该 view）或 frame 不可用 → 跳过（不记账，区分 availability/decode/runtime skip）
- [x] 2.2 **记账顺序冻结**：`association → available-miss ledger → display diagnostics → fusion/debug serialization`；当前 tick 的 miss 状态必须先于该 tick 的 display diagnostics 构建完成

## 3. Recovery opportunity/episode 同步 + guidance fast path

- [x] 3.1 `multiview_joint_run.py` recovery opportunity/episode 建立（L252 处）：`binding.visibility not in {"weak","missing","lost"}` 的跳过判断替换为 `not is_target_recovery_eligible(binding, self.recovery_config.fast_recovery_enabled)`——fast path 触发的 guidance 同步建立 episode、计入 opportunity，消除幽灵 guidance
- [x] 3.2 `backend/app/vision/multiview/guidance.py`：`generate()` target eligibility（L96-99）替换为 `is_target_recovery_eligible`；fast path 触发的 `GuidanceDecision.trigger_source="available_miss"`（visibility age 触发为 `visibility_age`，同时满足优先 visibility_age）；`reason` 保持最终 decision reason（`target_not_missing / donor_* / prediction_uncertain / cooldown / geometry_unavailable / generated` 等），MUST NOT 把 fast path 语义塞进 reason
- [x] 3.3 `MultiViewJointRun.__init__`：注入 recovery_config 时同步 `policy` 的 fast path 布尔（沿用 `multiview_joint_run.py:104-110` 的同步模式），两处不得各自持有独立默认值；`fast_recovery_enabled=false` 时 predicate 回退到仅 visibility 判定
- [x] 3.4 cooldown 原样保持：`guidance_cooldown_ticks` 计数 key、单位解释（reference frame index 语义）、`commit()` 消费行为一律不动；不重新定义、不引入 time-based cooldown

## 4. 诊断联动

- [x] 4.1 `backend/app/vision/multiview/player_display_diagnostics.py`：漏斗行增加 `available_miss_streak` 字段（缺省 0），builder 从 `ViewBinding.consecutive_available_misses` 读取（在 ledger 之后构建，语义见 spec）
- [x] 4.2 `src/types/report.ts`：`PlayerDisplayDiagnosticsRow` 增加 `available_miss_streak?: number`（可选）；`MultiviewObservabilityPage` 诊断面板展示该字段（缺失按 0）

## 5. 测试与验收

- [x] 5.1 后端单测：`record_attempt` 幂等（同 tick 重复调用不重复记账）；attempt authority（`view_results` 无该 view 但 frame_status available → 不计 miss；frame 不可用 → 不计 miss；有 AssociationUpdate → 清零；attempted available 无 update → 递增）；`is_target_recovery_eligible`（visibility age / fast path / 双满足 / 开关关闭）
- [x] 5.2 后端单测：guidance fast path（`misses>=1` 且 observed 触发、无 miss 不触发、cooldown 仍生效、donor/uncertainty 门限仍生效、`fast_recovery_enabled=false` 回退现状）；`GuidanceDecision.trigger_source/reason` 分离（fast path 有资格但 donor 拒绝 → `trigger_source=available_miss, reason=donor_low_quality`）
- [x] 5.3 后端集成测试：`multiview_joint_run` 完整跑一遍（mock 或轻量 trace）验证——fast path 触发时 episode/opportunity 同步建立（无幽灵 guidance）、记账顺序（漏斗不晚一拍）、核心结果不破坏
- [x] 5.4 前端测试：诊断面板展示 `available_miss_streak`；缺失字段按 0 展示
- [x] 5.5 真实素材验收（`mvr_35ac365aec96` / job-95132a7a53）：报告 `fast_path_opportunity_count / fast_path_guidance_generated_count / fast_path_guided_success_count`；A/B 对比 `fast_recovery_enabled=false vs true`（同一素材同一配置），输出"首次 available miss tick → 首次 eligible tick → 首次 guidance generated tick → 首次 target recovery tick"；验证 00:07 P1 丢失期漏斗行 `available_miss_streak >= 1` 且 guidance 触发时机提前（若被 donor/uncertainty 门拦截则如实报告，不夸大）
