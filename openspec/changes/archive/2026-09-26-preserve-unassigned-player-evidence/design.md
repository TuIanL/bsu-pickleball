## Context

`ViewTrackingSession` 已经能生成未通过 `lock_only` formal eligibility 的 `candidate_detections`，但这些数据目前只进入 debug trace 和画面诊断；joint association 只接收具有稳定本地 `Player_N` 身份的正式观测。正式观测在 `ROSTER_ACTIVE` 后若无法分配，只增加 unresolved 计数，不保留后续恢复所需的跨 tick 证据。

需要在两条边界之间加入独立候选通道：候选观测不冒充正式 local identity，也不改变普通关联；当原正式观测链路暂时断开时，候选可以为已有 global 提供受门控的重新捕获证据。

## Goals / Non-Goals

**Goals:**

- 把具备有效场地投影的未锁定 track 作为独立候选输入 joint run。
- 跨 tick 保留有限期候选历史，并允许稳定、唯一且几何可行的候选恢复到已有 roster global。
- 候选恢复不能创建超出赛制人数的新 global，也不能仅凭单帧距离改写身份。
- 让候选恢复、隔离和过期状态进入正式质量产物。

**Non-Goals:**

- 不改变 detector、tracker、lock 的阈值或 P1–P4 的本地编号规则。
- 不将 candidate track 直接作为正式的 `Player_N` 绑定。
- 不用插值、预测或展示 overlay 填充正式轨迹缺口。
- 不回写或重跑已经完成的历史 Job。

## Decisions

### 候选观测与正式观测使用独立入口

joint run 为候选轨迹建立独立的运行时记录，携带 view、source frame、tracklet lineage、bbox、脚点、投影状态和质量信息。普通 association 仍只消费正式 `JointObservation`；候选不得作为 detector 已锁定或 local identity 已确认的证据。

备选方案是把候选直接标成 `Player_N` 并送入普通 association。拒绝此方案，因为它会绕过单视角锁定不变量，并可能把一次错框写成全场正式身份。

### 已确认名册只允许恢复既有 global

候选在同一 view 上必须跨多个相邻有效 tick 保持 tracklet 连续、场地投影有效，并且在可用 global 中有唯一、通过 uncertainty-aware geometry gate 的目标。恢复仅可绑定到既有 roster global；并遵循同 view 唯一性与 pending reassociation 规则。没有唯一目标、出现槽位冲突或几何不够时，继续隔离并等待新证据。

备选方案是恢复候选直接占用空闲槽位。拒绝此方案作为 ROSTER_ACTIVE 后的路径，因为可能制造第五名身份或挤掉已有球员。

### 候选记录有界且只在有效视角帧推进

候选记录按 `(view_id, tracklet_lineage_id)` 聚合，仅在该 view 本 tick 成功处理、且候选投影有效时推进连续性；超过配置 TTL 即过期。不可用帧不计作候选失败，也不增加 hit count。

### 正式身份锚点与候选恢复分开报告

候选恢复可以补充既有 global 的位置与 view evidence，但不能单独把 `slot_fallback` 变成 confirmed canonical mapping。质量产物分别报告 candidate recovery 与 canonical identity confirmation。

## Risks / Trade-offs

- [候选 tracklet 发生换人] → 采用连续帧、速度/几何一致性、一对一 assignment 和 reassociation hysteresis；不满足时保留 ambiguous。
- [投影误差造成错配] → 复用既有 canonical projector 与 uncertainty-aware gate，并要求与次优候选有明确 margin。
- [候选历史占用内存] → 使用每 view / tracklet 有界 TTL 与容量上限，任务完成后释放。
- [候选恢复覆盖不足] → 质量产物公开 eligible、accepted、ambiguous、expired 各阶段计数；不足时保留失败状态，不降低质量门槛。

## Migration Plan

无需数据库迁移。新增诊断字段采用可选字段并提供 schema version；历史 Job 缺少候选恢复字段时按 unavailable 处理，不伪造零值。若候选恢复在真实素材上导致身份互换，可通过配置关闭候选恢复，恢复原正式观测路径。

## Open Questions

- 恢复所需的最少连续候选 tick 与次优匹配 margin 需要用既有真实 trace 标定；实现先沿用候选/重关联配置，并把实际阈值写入诊断，不能在本变更中静默降低身份质量门槛。
