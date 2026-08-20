# fix-multiview-single-view-fallback Design

## Context

job-60fcf4de8c（男双 sync_20260720_122645_317228）双摄分析产物三方对账：

- `tracking_overlay.json`（cam_1）：Player_2 自 19.467s 起连续检测，26.4s 后 90% 帧 conf≥0.5，全程仅 4 个短断帧（总 1.4s，最长 0.57s）——**检测层无问题**。
- `fused_player_trajectory.json`：`players` 仅 `global_player_1/2/3`，**global_player_4 零 sample**。
- `fused_player_overlay.json`：P2 渲染来源为 `cross_view_projected`（donor=cam_2），26.233s 起永久消失（bbox 记忆老化 + donor recency 超限后无融合证据供给）。
- `roster.json`：`global_player_4 = Player_2` 仅 cam_1 binding 且 `visibility="lost"`，cam_2 无 binding。

代码层根因（`association_global.py:228/287` + `global_state.py:483-534`）形成死循环：

```
update_stale_eligibility: global_player_4 last_seen 陈旧 → association_eligible=False
        │
        ▼
predict_all() 不返回 global_player_4（仅非 stale）
        │
        ▼
min_cost_matching 的 pred_globals 不含 global_player_4 → cam_1 观测无法分配给它
        │
        ▼
fused dict 无 global_player_4 → joint_run 不 absorb_measurement → last_seen 永不刷新
        │
        ▼
下一 tick 仍 stale → 循环（P2 永远无法通过普通关联进入融合）
```

弱历史绑定路径（`association_global.py:430-471`，理论上可含 stale 玩家）存在但未生效——证据是 fused trajectory 中 global_player_4 完全无 sample，且 `fused_diagnostics.json` 无任何 global_player_4 关联决策。overlay 层 P2 从未靠 cam_1 自身检测渲染（base_observed 仅出现在 19.5s 后少数帧），一直依赖 cam_2 donor 投影，一旦 donor 断供即永久消失。

## Goals / Non-Goals

**Goals:**
- 单视图 binding 的 roster 球员（仅 cam_1 持续观测、cam_2 缺失）SHALL 产出 fused measurement（`fusion_status=single_view_fallback`），进入 fused trajectory。
- fused overlay SHALL 在 cam_1 单边 strong observation 时以 `base_observed`/`REAL_BOX` 渲染该球员，不依赖 cross-view donor。
- `fused_diagnostics` 的 `single_view_fallback` 计数 SHALL 反映真实单视图路径使用量（当前=2，形同虚设）。
- stale 门控 SHALL 区分"单视图持续活跃"与"跨视图缺失"——后者不得使单视图活跃玩家失去关联资格。
- 每类修复配套回归测试，且用同源 session 重跑验收。

**Non-Goals:**
- 不改变 fused trajectory / overlay / diagnostics 产物 schema 与对外 URL。
- 不解决 YOLO 检测召回率问题（P2 首检测延迟至 19.5s 是 bootstrap 漏锁历史问题的残余，已由 fix-multiview-cam1-bootstrap-4player 处理，不在本 change 范围）。
- 不改变 `dual_observed` 加权融合逻辑（仅扩展 `single_view_fallback` 可达性）。
- 不引入新的外部依赖。

## Decisions

### D1: stale 门控增加"单视图活跃豁免"——跨视图缺失 ≠ 失去关联资格

**方案**：`GlobalPlayerRegistry.update_stale_eligibility` 判定 stale 时新增豁免分支：若玩家存在任一 view binding 且 `last_seen_s` 新鲜（`now_s - last_seen_s <= stale_last_seen_s`），则该玩家 SHALL 保持 `association_eligible=True`，即使其他 view binding 缺失/过期。

```python
# global_state.py update_stale_eligibility
def update_stale_eligibility(self, now_s: float) -> None:
    for state in self.players.values():
        if state.roster_status is None:
            continue
        any_view_fresh = (
            any(b.visibility in ("observed", "weak") for b in state.view_bindings.values())
            and state.last_seen_s is not None
            and (now_s - state.last_seen_s <= self.stale_last_seen_s)
        )
        # 豁免仅作用于 last_seen 维度；uncertainty 门控保持独立（不可靠预测不吸附观测）
        stale = state.position_uncertainty_ft > self.stale_uncertainty_ft or (
            state.last_seen_s is not None
            and now_s - state.last_seen_s > self.stale_last_seen_s
            and not any_view_fresh
        )
        state.association_eligible = not stale
```

**备选对比**：
- A（选）：单视图活跃豁免。改动最小，直接解除死循环入口（predict_all 放行）。
- B：在 association 层为 stale 玩家单独开"几何邻域回退分配"。绕过 predict_all 过滤，但引入第二条分配路径，与 min_cost_matching 并存易出双路径语义分歧。
- C：joint_run 层对 fused 缺失但单视图活跃的玩家补 sample。治标不治本——不刷新 last_seen，下 tick 仍 stale。

选 A：从根因入口解环，predict_all → matching → fused → absorb 的既有链路不变。

### D2: fusion 对单视图活跃玩家产出 `single_view_fallback` sample

**方案**：D1 生效后，单视图活跃的 global_player_N 回到 `predict_all` 输出 → `min_cost_matching` 可将其 cam_1 观测分配给它（continuity 或普通匹配）→ `fused` dict 包含该 gid → `multiview_joint_run.py:599` 既有逻辑自动产出 `fusion_status="single_view_fallback"`（`len(views) >= 2` 时为 dual，否则 fallback），`metric_eligible=True` 保持（真实观测）。

无需改 joint_run 的 sample 生成逻辑——**D1 是充分条件**。本决策只要求验收时确认 sample 生成路径按既有代码生效，并为 `single_view_fallback` 计数增加按 player 归因的断言（fused_diagnostics）。

**备选对比**：
- A（选）：仅 D1 + 验收断言。改动最小，复用既有融合管线。
- B：joint_run 增加单视图 sample 兜底循环。防御性更强但重复逻辑，且绕过 association 的 binding 语义，可能产生"无绑定也出 measurement"的虚假样本。

选 A：单视图 sample 必须有 binding 支撑（观测被真实分配到该 gid），避免无证据输出。

### D3: overlay 数据源覆盖 single_view_fallback sample

**方案**：`fused_player_overlay` builder 的数据源（final fused trajectory + roster map）已含 single_view_fallback sample 后，分支决策链自动命中 `base_observed`（reference view 有 F0 strong observation）→ `REAL_BOX`。需验证 overlay builder 对 `single_view_fallback` sample 的 `view_observations` 字段读取（reference 路 available 即可），若存在读取缺口则补一行透传（composer / builder 数据源构造处）。

**备选对比**：
- A（选）：依赖 fused trajectory 完整化，overlay 逻辑零改动（仅验证）。
- B：overlay 直接读 cam_1 tracking 数据补渲染。绕过 fusion 语义，与"fused overlay 取代本地检测"的既有 spec 冲突。

选 A：保持"fused overlay 数据源唯一"的既有架构约束。

### D4: metric_eligible 与质量门控

**方案**：`single_view_fallback` sample 默认 `metric_eligible=True`（真实观测、可进指标），但通过 `OverlayBuilderConfig`/`FusionConfig` 增加可配置门控（如 `single_view_metric_eligible: bool = True`、`single_view_min_quality: float | None = None`），允许在需要时按单视图观测 quality 过滤。`metric_eligible` 语义不变：`predicted` 永不进指标，真实观测（含单视图）可进。

**备选对比**：
- A（选）：默认放行 + 可选门控。双视图确认的 P3/P4 类球员指标不受影响；P2 类球员获得完整指标（速度/覆盖/停留），符合"真实观测可进指标"既有 spec。
- B：单视图样本一律 `metric_eligible=False`。保守但会让 P2 类球员指标全空，与产品目标（完整性）相悖。

选 A：默认放行，门控留作逃生阀。

## Risks / Trade-offs

- [单视图 sample 质量低于 dual_observed] → 以 `fusion_status=single_view_fallback` 显式标注（既有 schema 已支持），前端/指标层可区分；`metric_eligible` 门控可关。
- [stale 豁免让短暂离场玩家占用关联预算] → 豁免前提是"任一 view binding 新鲜（observed/weak）"，离场即 binding 过期 → 失去豁免 → 恢复原 stale 语义，不会无限占用。
- [单视图路径可能放大误检（把场边人员当球员）] → 观测必须经 `set_binding` 槽位唯一性 + continuity/几何门才分配；单视图 sample 的 confidence 经 `intrinsic_quality` 参与质量加权，低质观测权重低。
- [与 fix-multiview-cam1-bootstrap-4player 的既有约束冲突] → 不冲突：bootstrap 约束管"锁定槽位不可替换"，本 change 管"已锁定槽位在单视图下持续产出"，两者正交。

## Migration Plan

1. 后端：D1（stale 豁免）+ 单测（构造单视图活跃玩家 → predict_all 返回 → association_eligible=True）。
2. 后端：D2 验收断言（fusion 单视图连续性单测：单视图观测 N 帧 → fused trajectory 产出 N 个 single_view_fallback sample 且按 player 归因）+ fused_diagnostics 计数单测。
3. 后端：D3 overlay 验证（cam_1 base_observed 高置信 → overlay REAL_BOX，即使 cam_2 binding 缺失）+ 数据源透传补缺（如有）。
4. 回归：`pytest backend/tests/`（新增/既有 multiview 测试）+ `npm test`（前端无 schema 变更，仅确认不回归）。
5. 验收：用 job-60fcf4de8c 同源 session（sync_20260720_122645_317228）重跑 joint job，核验：fused trajectory 含 global_player_4、fused_diagnostics.single_view_fallback>0 且可归因、overlay P2 全程可见（REAL_BOX 为主）。
6. 回滚：D1 独立提交可单独回滚；D3 若有透传改动独立提交。

## Open Questions

- 弱历史绑定（`association_global.py:430`）为何未把 cam_1.Player_2 带回 global_player_4：需查 `historical_bindings` 是否含 `(cam_1, Player_2)` 记录、26.2s 断帧时 binding lost 是否清除了历史绑定、以及 predict_for 的预测位置与观测几何距离是否超 gate。若 debug trace 可证该路径本应生效，D1 之外可能还需修 historical_bindings 的保留策略（后续 debug trace 验证后决定）。
- `stale_last_seen_s=10.0` 在双打 4 人场景是否过严：单视图豁免后该阈值只影响"全视图离场"场景，暂不改默认值，留待数据验证。
- 单视图 sample 的 `fusion_confidence` 语义：当前为 association confidence 或观测质量，需确认单视图路径下 `fuse_assignments` 的 confidence 输出是否合理（验收时检查）。
