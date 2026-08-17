## MODIFIED Requirements

### Requirement: PreparedViewFrame 事务型两阶段

`ViewTrackingSession` SHALL 提供事务型两阶段调用：`prepare_frame(frame, frame_index, timestamp, pre_tick_guidance)`（base YOLO → ROI filter → pre-tick guided ROI → merge，**不调用 tracker.update**，产出 `PreparedViewFrame` 含 `committed=False`）与 `complete_frame(prepared, same_tick_guidance)`（same-tick guided merge → **tracker.update 恰好一次** → projector → selector → lock → identity → frame_detections，置 `committed=True`）。**第二次 complete 同一 prepared 帧 SHALL 抛异常**。原 `step(frame, ..., guidance=())` SHALL 保持兼容旧调用（内部调 prepare_frame(pre_tick_guidance=guidance) + complete_frame(空 same_tick)）。`PreparedViewFrame` SHALL 保存 `raw_detections`（仅诊断）与 `roi_filtered_base` / `pre_tick_guided` / `merged_pre_tick`（参与 pre-association 的 evidence，保留 origin provenance）。

#### Scenario: prepare 不 update tracker

- **WHEN** 调用方执行 `prepare_frame(frame, ...)`
- **THEN** 系统 SHALL 完成 base/ROI/pre-tick guided/merge
- **AND** SHALL NOT 调用 tracker.update

#### Scenario: complete 后 committed 且一次 update

- **WHEN** 调用方执行 `complete_frame(prepared, same_tick_guidance)`
- **THEN** 系统 SHALL merge → tracker.update 一次 → 后续链路
- **AND** `prepared.committed` SHALL 置 True

#### Scenario: 重复 complete 抛异常

- **WHEN** 调用方对同一 prepared 帧第二次调用 `complete_frame`
- **THEN** 系统 SHALL 抛出异常
- **AND** SHALL NOT 再次 update tracker

#### Scenario: step() 兼容旧调用

- **WHEN** 旧调用方使用 `step(frame, frame_index, timestamp)`（无 same-tick guidance）
- **THEN** 行为 SHALL 与实施前一致（base + pre-tick guidance → 一次 tracker.update）

### Requirement: tracker.update-once 精确语义

系统 SHALL 保证：**successfully prepared and committed source frame → 每 view 恰好 1 次 tracker.update；任何 source frame → 至多 1 次**。frame unavailable / decode fail / view degraded 时 SHALL 为 0。

#### Scenario: 正常帧恰好一次

- **WHEN** 某 view 的 source frame 成功 prepared 且 committed
- **THEN** 该帧该 view 的 tracker.update 次数 SHALL 恰为 1

#### Scenario: 不可用帧为 0

- **WHEN** 某 view 的 frame unavailable / decode fail / view degraded
- **THEN** tracker.update 次数 SHALL 为 0
- **AND** 该情况 SHALL NOT 计入"恰好 1"要求
