## Context

P1-0 已冻结 canonical clock、per-view `FrameSample`、timing authority 与 frame availability。现行 `joint_tracking_v2` 在同一 tick 内有 barrier，但 guidance 只生成给 secondary view，运行实体持有 reference view 的全局 frame size 与 inverse homography；`ViewBinding` 仅在新 observation 到来时更新；adapter 将 formal local identity 与 guided provenance 丢弃。关联器还允许历史 mapping 绕过几何门，并能把同一 view 的两个 unmatched observation bootstrap 为同一 global。

本设计只使 P1 online recovery operational。`late_fusion_v1`/P0、单摄默认行为、offline refinement、模型替换和最终 fusion weight 不在范围内。P1-0 的 timing authority、availability 与 provenance 是本 Change 的输入前提，不能被重新解释或绕过。

## Goals / Non-Goals

**Goals:**

- 让任一可信 base view 能对另一 weak/lost 且当前 frame 可用的 view 发起 guidance，并确保两路 perception 只消费同一个 pre-tick snapshot。
- 将 donor、guidance、target real-pixel candidate、pre-gate、tracker assignment、lock/local identity 与 global reassociation 组成可审计证据链。
- 保持 geometry hard gate 的权威性，允许 identity/guidance 仅在可行候选间提供 continuity prior。
- 将 per-view timing/geometry 与恢复漏斗写入 v2 artifact 和 diagnostics。

**Non-Goals:**

- 不让 guidance 或 prediction 制造 measurement，也不允许 guided evidence 建立 anchor 或成为强 donor。
- 不升级 `fused_player_trajectory` 主版本，不改变 P0 关联器或 late-fusion 算法语义。
- 不将 target frame unavailable 解释为视觉漏检或 recovery opportunity。

## Decisions

### D1: pre-tick snapshot 与双向对称

每 tick 固定为 `age bindings -> predict -> build guidance snapshot -> all view perception -> barrier -> associate/fuse -> state(t)`。所有 view 只能读取同一份 snapshot，禁止 Cam1 的结果影响同 tick Cam2。reference view 仍拥有 canonical clock 与 full-analysis owner 职责，但不拥有 donor 特权。选择 snapshot 而非串行即时反馈，是为了让结果与 runtime 遍历顺序无关。

因此 pre-tick binding 为 weak 时，即使 target 的 same-tick base detection 已恢复，ROI 仍可被调用；实现不得先处理某一路 base detection 再决定另一路 guidance。若 base 与 guided 在同一 target 命中同一人，base evidence 胜出，记录为 `base_recovered` 而非 guided recovery success。

### D2: per-view runtime context

`JointViewRuntime`/`MultiViewJointRun` 以 view map 持有 width、height、homography/inverse、orientation、timing provider。每个 target ROI 使用自身 `canonical -> local -> H^-1 -> image`。共享 reference geometry 会在异分辨率或不同标定视角产生错误 ROI，因此不保留为 joint-wide source of truth。

legacy adapter fallback 仅适用于单摄、late fusion 或 compatibility 路径。P1 online guidance 缺少 target geometry 时 SHALL 记录 `recovery_skip_missing_target_geometry`，不得以 reference view 的 transform 或 size 代替。

### D3: binding aging、availability 与 donor

registry 每 tick 以 take time 执行 `age_bindings()`，将 observed 变为 weak/lost，并保存最后一份 view evidence（local identity、track、quality、origin、source frame、lock/tracking state、guidance）。但只有 target `FrameSample` 为 `available` 时，weak/lost 才构成 recovery opportunity；不可用帧记录 timing/availability skip，不运行 ROI 且不消耗 cooldown。

强 donor 必须来自不同 view 的 recent `base` observation，且 global 为 confirmed + cross-view anchored、uncertainty 和 donor intrinsic quality 符合阈值。`guided_roi` 仍是真实 measurement，可参与融合和指标，但不能作为 donor 或增加 anchor，防止 self-confirming feedback loop。

### D4: local-space pre-gate 与精确 provenance

target detection 在源帧上执行，候选临时 footpoint 先投影到 target local court space，并与 guidance 的 `predicted_local_position` 比较 residual。canonical transform 留给 global association，避免 orientation 混用。

pre-gate 输出 candidate evidence（guidance id、expected global、donor、local position、residual、reject reason）。merge 在 `DetectionEvidence` 层完成：base 与 guided 重合时 base 优先且 guided 标记 `duplicate_of_base`；多个 guided 候选重合时按更小 residual、再 donor quality、再稳定 guidance id 选择唯一 evidence。tracker 新增兼容的 assignment-aware update，原 `update()` 委托它并保持返回值；assignment 后还必须按 `DuplicateTrackSuppressor` 最终 surviving track IDs 过滤 evidence，因此 provenance 不会遗留在已抑制的 track 上。

### D5: joint formal identity boundary

`ViewTrackingSession` 增加 `legacy_union | lock_only` eligibility policy：单摄/late fusion 保持 legacy union，joint 使用 lock-only。joint adapter 从 formal `frame_detections` 中选择具 stable `player_id` 与 `identity_epoch` 的条目，再按 track join position；不再遍历所有 `frame_positions`。权威 continuity key 为 `(view_id, player_id, identity_epoch)`，epoch 变化时旧 mapping 必须失效。这保证 guided candidate 即使被 tracker 接住，也必须通过 lock 与 local identity 才能进入 global。

### D6: association prior 不突破几何门

`JointViewObservation` 成为 runtime 唯一 observation contract。关联先使用 canonical distance 执行 hard feasibility gate；仅对通过者加入 local identity switch penalty 和 guided expected-global mismatch penalty。已有 mapping 的 unmatched fallback 也必须过相同 hard gate。tentative bootstrap group 每 tick 每 view 至多一个 observation；anchor 只接受 distinct views 的 base+base 一致证据。

### D7: artifact、config 与诊断

使用集中 `P1OnlineRecoveryConfig` 固化 aging、donor、uncertainty、ROI、pre-gate、association/reassociation 参数并写入 manifest/input signature。v2 `view_observations` additive 地写入 local identity、identity epoch、track、origin、guidance、donor、residual、intrinsic quality 和 P1-0 timing fields。

每次 target 进入 weak/lost 创建 `recovery_episode_id`，直到恢复 formal target observation 为止。`recovery_opportunity` 要求 target frame available、weak/lost、global confirmed+anchored 与可接受 uncertainty；`guidance_generated` 还要求合格 base donor；`guided_recovery_success` 必须经过真实 guided pixel evidence、pre-gate、surviving tracker、formal lock/local identity，并分配回 expected global。same-tick base recovery 记 `base_recovered`，不算 guided success。cooldown 仅在 source frame 成功 decode 且实际调用 `detect_regions` 后消费；geometry 缺失、decode 失败或 ROI detector 不可用只记录 skip/error。历史 reader 对新增字段使用兼容默认值。

## Risks / Trade-offs

- [lock-only 降低 joint 初期观测数量] → 这是 deliberate safety gate；通过 controlled dropout 验证恢复的是 formal player 而非短暂 track。
- [per-view geometry 改动 executor wiring] → 先以双视角不同 size/transform fixture 覆盖，再保留 legacy adapter fallback。
- [base-only donor 可能降低短期 recall] → 换取首版不自证；guided evidence 晋升留给后续实验 Change。
- [更丰富 artifact 增大体积] → 只写 observation-level 最小 provenance，保持 v2 additive 与历史读取兼容。
- [target unavailable 后 binding 变陈旧] → 诊断区分 unavailable skip 与像素中 missing，且前者不产生 opportunity/cooldown 消耗。

## Migration Plan

1. 先添加 contracts/config、per-view context、assignment-aware tracker 与单元 fixtures，保持默认 policy 不变。
2. 接入 joint lock-only adapter、aging、donor-aware guidance、association hardening 和 diagnostics。
3. 以双向 controlled dropout、negative cases、legacy regression 与 P1-0 timing regression 验收。
4. 回滚时关闭 P1 online recovery 或选择 `late_fusion_v1`；保留 additive v2 fields 和已经写出的 artifacts，不迁移或删除历史数据。

## Open Questions

- donor freshness 和 quality 阈值以真实 CaptureTake 的 sensitivity sweep 冻结；本 Change 先冻结语义和配置可追溯性。
- 多于两路 view 的 donor ranking 采用最高 intrinsic quality 还是显式优先级，留待双摄闭环验证完成后决定。
