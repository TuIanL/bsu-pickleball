## ADDED Requirements

### Requirement: JointViewRuntime prepare/complete 窄接口

`JointViewRuntime` SHALL 提供 `prepare(source_frame_index, timestamp_s, pre_tick_guidance, timing_context) -> PreparedViewFrame | None` 与 `complete(prepared, same_tick_guidance, timing_context) -> ViewFrameResult | None` 窄接口。`prepare` SHALL 解帧**恰好一次**（复用现有 `get_frame`，含 `CAP_PROP_POS_FRAMES` 修复）后转发 `tracking_session.prepare_frame`；decode 失败 SHALL 返回 None。`complete` SHALL 转发 `tracking_session.complete_frame`（保持 committed 防重复语义）。主循环 MUST NOT 越过 runtime 直接解帧；same-tick 阶段 MUST NOT 重复解同一 source frame。原 `step()` SHALL 保留兼容旧调用（内部 prepare + complete 空 same-tick）。

#### Scenario: prepare 解帧一次

- **WHEN** 主循环调用 `runtime.prepare(source_frame_index, ...)`
- **THEN** runtime SHALL 解帧恰好一次并转发 prepare_frame
- **AND** SHALL NOT 在 same-tick 阶段重复解同一帧

#### Scenario: decode 失败返回 None

- **WHEN** `get_frame` 解码失败
- **THEN** `prepare` SHALL 返回 None（记为 decode skip，update 次数为 0）

#### Scenario: complete 保持 committed 语义

- **WHEN** 主循环调用 `runtime.complete(prepared, same_tick_guidance, ...)`
- **THEN** runtime SHALL 转发 complete_frame（committed 防重复 update 保持）
