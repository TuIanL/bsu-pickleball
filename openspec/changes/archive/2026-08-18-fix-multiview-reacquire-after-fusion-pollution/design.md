# fix-multiview-reacquire-after-fusion-pollution — Design

## Context

男双双摄 joint 任务（job-60fcf4de8c / job-e8eda229bf，cam_1=reference 174/identity + cam_2=175/rotate_180）中 `global_player_4`（=cam_1/Player_2）在 26.2s 永久消失。实测证据链（f0 snapshot，新任务重跑与旧任务字节级一致）：

```
25.83s   cam_2 间歇输出空间离群观测 [7.4,33.6]（真实应 [19.9,-3.1]，差 40ft）
         quality 0.81 vs cam_1 0.31 → conflict 仲裁按 raw confidence 选 cam_2
25.83-26.20s  P4 全局位置被 cam_2 污染（gpos 从 [19.8,-3.4] 跳至 [7.2,34.3]）
26.00s   cam_1 检测断帧 0.4s；26.23s cam_2 也全丢失 → 双视图全 missing
26.23s+  P4 估计器无观测自由漂移（[16.2,8.5]→[11.9,18.1]）
26.367s  cam_1/Player_2 恢复检测（真实 [19,-4]），但 P4 预测已漂至 [15.7,9.5]
         residual ≈ 14ft > max_reacquire_gate_ft(8.0) → 普通匹配拒绝
         → continuity 同门拒绝 → historical binding 同门拒绝 → roster 满 → unresolved
         此后 1028 帧观测全 missing → 永久丢失
```

**根因分级**（经代码核验）：
- **Root Cause A（首要）**：`fuse_assignments()` 冲突时 `us = [max(us, key=lambda u: u.observation.confidence)]`——raw confidence winner-takes-all。`pair_consistency()` 调用时 `predicted=None`，且其 `residual_to_prediction_ft` 语义为**两路最小 residual**（非 per-view），无法支撑仲裁。**spec（trajectory-fusion 冲突检测）已要求"按全局预测或高质量单视角选择输出"，实现与 spec 偏差。**
- **Root Cause B（永久消失直接原因）**：污染后的 Global Kalman 预测与恢复后的正确观测相距 14ft > 8ft，普通匹配、continuity、historical reacquire 共用同一 `_pair_gate_ft` 硬门，正确 identity 永远回不到原 global。
- **Root Cause C（放大因素）**：`absorb_measurement()` 无条件刷新 `last_seen_s`/`roster_confirm_ticks` 且 `GlobalMotionEstimator.update` 固定 `measurement_noise=1.0`——污染 measurement 一旦进入即整体拉走位置与速度，并让系统误以为"真实看见"。
- **非根因**：stale eligibility（D1 已修，`fix-multiview-single-view-fallback`，P4 全程在 predictions 1784/1815 ticks）；cam_1 YOLO 检测（26.367s 已恢复）；overlay renderer（无 fused sample 时仅下游表现）；F1 refinement（多恢复约 1s 未解决 F0 identity chain）；Selector 绕过 lock（executor 已 `eligibility_policy="lock_only"`）。

约束：`max_plausible_distance_ft=3.0`（conflict 门）保留；`max_reacquire_gate_ft=8.0` **不整体放宽**（避免放大双打 P1/P2、P3/P4 互换风险）。

## Goals / Non-Goals

**Goals**
- G1 冲突仲裁 prediction-aware：显式 per-view residual 仲裁，confidence 仅作证据之一。
- G2 错误 measurement 不再污染 Global Kalman：innovation guard 拒绝灾难性跳变，且 reject 不刷新任何真实测量状态。
- G3 污染后安全恢复：可信历史 identity 在满足明确条件时 reanchor，决策（associator）与执行（JointRun）分离。
- G4 事故可诊断：counters 与结构化 decision trace 分层。

**Non-Goals**
- 不改 `max_plausible_distance_ft`（保持 3ft）。
- 不整体提高 `max_reacquire_gate_ft`。
- 不改 late-fusion pipeline（P0 `GlobalTrackFilter`/`fuse_observation` 路径不动）。
- 不做 quality-aware measurement noise 全量重设计（仅第一版最小 guard：reject；R 动态化留后续）。
- 不引入 predicted trajectory sample 功能（`both implausible` 时本 tick 不产 metric sample，prediction 仅留 runtime state/debug）。
- 不触碰 roster 重建 / bootstrap 逻辑。
- 不新建 capability（conflict arbitration 属 `multiview-player-trajectory-fusion` 既有职责）。

## Decisions

### 工程契约 1（贯穿 D1/D3）：state update owner 唯一

`GlobalPlayerRegistry` 的 estimator/state 写入**只允许**由 `MultiViewJointRun` 在 fusion 之后执行（现有架构已如此）。associator（`process_tick`/`fuse_assignments`）SHALL NOT 直接调用 `absorb_measurement`/`reseed`。本 change 所有新逻辑遵守该边界。

### D1 — Prediction-aware conflict arbitration（Root Cause A）

`fuse_assignments()` 由 `@staticmethod` 改为 instance method：

```python
def fuse_assignments(self, updates, include_tentative=True, predictions=None):
    # predictions: dict[gid, (x, y, uncertainty_ft)]  —— pre-tick 冻结预测
```

冲突仲裁（inter_view_distance > `max_plausible_distance_ft`）时**显式计算**：

```python
r_cam1 = dist(cam1_xy, pred_xy)
r_cam2 = dist(cam2_xy, pred_xy)
gate   = min(self.max_reacquire_gate_ft, self.base_gate_ft + self.uncertainty_scale * unc)
plausible(v) = r_v <= gate
```

决策树（prediction residual 主导，intrinsic 仅辅助）：

```
仅一路 plausible            → 选 plausible 路
两路 plausible 且 |r1-r2| > residual_margin_ft(默认 2.0)
                            → 选 residual 更小的一路
两路 plausible 且 |r1-r2| <= residual_margin_ft
                            → intrinsic_quality 仲裁（质量接近再 continuity/binding tie-break）
两路都不 plausible          → conflict_no_measurement：不产出 fused entry
                              （JointRun 无 fused → 不 absorb → 本 tick 无 metric sample；
                                prediction 仅留 runtime state/debug，不写 trajectory sample）
```

`pair_consistency()` **不改**：仅保留 inter-view/conflict 检测职责（其 `residual_to_prediction_ft` 是两路最小值，不用于仲裁）。D1 内部显式算 `r1/r2` 最稳，避免与既有语义纠缠。

**为什么 prediction residual 优先于 intrinsic**：一旦进入跨视图 conflict，global temporal continuity 是主证据——`0.81 > 0.31` 的旧问题不能变成 `0.87 intrinsic > 0.42 intrinsic` 的新问题。intrinsic 只在 residual 接近时仲裁，避免单视角质量误导。

**为什么 pre-tick prediction**：tick barrier 前冻结，不包含当前 tick 观测，避免被污染状态自我背书。

### D2 — Global measurement innovation guard（Root Cause C）

**不在 estimator 层做策略**（保持 `GlobalMotionEstimator` 单纯：predict→Kalman update→写 state）。在 Registry 层：

```python
class MeasurementUpdateResult:
    accepted: bool
    x_ft: float; y_ft: float
    innovation_ft: float | None
    gate_ft: float | None
    reason: str | None   # "innovation_rejected" | None

# GlobalPlayerRegistry.absorb_measurement() 前置 guard：
pred = estimator.predict(gid, t)  # 若不可预测则直接 accepted
innovation = dist((x,y), pred_xy)
gate = max(innovation_floor_ft, innovation_uncertainty_k * pred_uncertainty_ft)
       # innovation_floor_ft 独立配置（首版取 8.0），不与 association 的 max_reacquire_gate_ft 绑定
if innovation > gate:
    rejected: 不调 estimator.update；不刷新 last_seen_s；不增 roster_confirm_ticks；
              不更新 position/velocity/uncertainty；返回 accepted=False
else:
    accepted: 走现有 update 路径；返回 accepted=True
```

**reject 语义是"这一帧没看见"**：拒绝后 `last_seen_s` 不刷新 → stale eligibility 正常推进 → roster confirmation 不虚增 → 与 D1 的 `conflict_no_measurement` 在状态语义上一致。

**为什么 reject 不降权**：降权需重调 Kalman 噪声参数，风险大于收益；reject 足以阻断污染链，且单测可确定性验证。R 动态化（按 intrinsic/innovation 缩放 measurement_noise）留后续。

**为什么独立命名 `innovation_floor_ft`**：reacquire gate 是 association policy，innovation guard 是 state estimation safety policy，首版数值都可为 8ft，但架构上不绑死。

### D3 — Trusted Historical Identity Reanchor（Root Cause B）

**决策与执行分离**：

```
associator.process_tick()
    → 弱历史绑定分支前评估 reanchor 五条件
    → 满足 → AssociationUpdate(..., reanchor=True)（不 reseed、不 absorb）
fuse_assignments()
    → reanchor update 正常参与 fusion，产出可信 measurement
MultiViewJointRun()
    → if update.reanchor: registry.reseed(gid, x, y, t)   # 唯一执行点
    → else:            registry.absorb_measurement(...)
```

reanchor 五条件（全部满足）：

```
1. 观测 (view_id, view_player_id) 存在弱历史绑定 → global G（historical_bindings）
2. G 处于 risk 状态（last_state_risk_tick 在 reanchor_risk_window_ticks 内，reason ∈ {innovation_rejected, conflict_no_measurement}）
3. local identity 当前稳定（同 view_player_id 连续出现，无 epoch 抖动）
4. 观测连续 N 帧（N=3，可配置）在自身运动连续邻域（帧间位移 < 3ft）
5. 无歧义：该观测对 G 的 residual 显著小于对次优 global 的 residual（margin），或次优不在候选/已绑定
```

**reseed 语义锁定（第一版）**：`position = current observation`、`velocity = 0`、`covariance = initial/reseed covariance`、`timestamp = current`。宁可下几个 tick 重新学习速度，也不带入污染前的速度；velocity 由候选轨迹估计留后续版本。

**为什么决策与执行分离**：若 process_tick 内直接 reseed 又返回 update，JointRun 会再次 absorb → 同 tick 双重 state update；若 reseed 后不返回 update 则无 fused sample/overlay/trajectory。reanchor 是关联决策，state update 必须由 JointRun 唯一执行。

**为什么不用宽门（8→16ft）**：双打中相邻球员间距常在 5–15ft，宽门放大 P1/P2、P3/P4 互换；reanchor 以"历史绑定+risk 状态+连续稳定+无歧义+运动连续"换取安全性，宁可漏不误换。

**risk 状态生命周期（非永久 boolean）**：

```
last_state_risk_tick: int | None
state_risk_reason: innovation_rejected | conflict_no_measurement | None
reanchor_risk_window_ticks = N（默认 90，约 3s）
clear 条件（任一）：
  - 连续 M 帧（M=5）clean accepted measurement（无 reject / 无 conflict 未选中）
  - reanchor_succeeded
  - last_state_risk_tick 距今 > reanchor_risk_window_ticks
```

### D4 — Fusion / Innovation / Reanchor 可诊断事件（分层）

```
associator.diagnostics: dict[str, int]          # 纯计数（现有机制扩展键）
  fusion_conflict / fusion_conflict_cam1_selected / fusion_conflict_cam2_selected /
  fusion_conflict_prediction_selected / fusion_conflict_no_measurement
  measurement_innovation_rejected
  reanchor_pending / reanchor_succeeded / reanchor_rejected_ambiguous

associator.last_tick_fusion_decisions: list[dict]  # 当前 tick 结构化明细
  {global_player_id, timestamp, cam1_xy, cam2_xy, inter_view_distance,
   r_cam1, r_cam2, intrinsic1, intrinsic2, gate, selected_source, reason}

MultiViewJointRun debug trace                              # 逐 tick 详细证据（既有机制）
fused_diagnostics（artifact.py）                            # 汇总计数 + 少量归因 summary
```

`artifact.py` 不做 runtime 重推导，仅把 JointRun 提供的 counters 原样落入 `fused_diagnostics`（必要时 schema 小改）。

## Risks / Trade-offs

- **[both implausible → 无 sample] 短暂丢失双视图样本** → 该帧 prediction-only（runtime state/debug 内），trade-off 是"宁可缺一帧也不污染 estimator"；只在真实冲突帧发生。
- **[reanchor 误锚]** 连续 3 帧+无歧义条件不绝对 → 观察 `reanchor_rejected_ambiguous` 计数；真实 trace 若现误锚，收紧 N 或增加 donor-view 一致性要求。
- **[innovation guard 拒合法机动]** → `innovation_floor_ft` 保底 + uncertainty 缩放；acceptance 窗口 24–30s 回归验证 P4 真实轨迹不被误拒。
- **[D1 排序维度多]** → 决策树锁死（residual 主导 → intrinsic → continuity），单测固定三个决策场景。
- **[reject 后 stale 判定变化]** → 语义对齐：reject/conflict_no_measurement 均不刷新 last_seen，stale 推进一致；`fix-multiview-single-view-fallback` 的单视图活跃豁免仍生效（observed binding 且 last_seen 新鲜 → 不 stale），需 regression 测试确认。

## Migration Plan

1. D1 回归先行：`test_conflict_poison_rejects_cam2_outlier`（失败态）→ 实现 D1 → 通过。
2. D2 回归先行：`test_innovation_guard_rejects_catastrophic_jump`（失败态）→ 实现 → 通过；补 `test_innovation_reject_does_not_refresh_last_seen`。
3. D3 回归先行：`test_reanchor_restores_after_pollution`（失败态）→ 实现（决策+执行分离）→ 通过；补 ambiguous / not-tainted 用例。
4. D1 regression：`test_single_view_active_not_stale_regression`（防回退 stale 修复）。
5. 全量 pytest（multiview 相关）+ npm test。
6. 真实 60s acceptance（外接盘挂载后重跑同源 joint job），验收指标见 tasks 5.4/5.5——**不强求 `reanchor_succeeded`**（D1 修好后大概率无需 reanchor），**不要求 fallback count 下降**（P4 活得久反而可能增加 fallback）。
7. 失败回滚：仅回退本 change 代码（独立提交），spec delta 随代码 revert；D1（stale 修复）独立保留。

## Open Questions

1. cam_2 在 25.83s 为何间歇输出 [7.4,33.6] 离群观测——检测层误检（球/影子/相邻球员）还是投影/标定问题？D4 的 `fusion_conflict_*` 明细给首帧证据；若属检测层系统性误检，后续独立 change（检测侧置信度惩罚）。
2. `residual_margin_ft`（默认 2.0）与 `reanchor_risk_window_ticks`（默认 90）需真实 trace 标定——先保守值，acceptance 后按 P4 实际恢复轨迹调整。
3. reanchor 的 N=3 帧与"运动连续邻域 3ft"阈值需 trace 标定；velocity=0 若导致明显抖动，后续用三帧候选轨迹估计 velocity（不进第一版）。
4. D1 改造后 `fuse_assignments` 与 late-fusion 冲突语义是否重复——本 change 先内聚，观察重复度后再抽象共享仲裁函数。
