## 1. Timing authority 契约

- [x] 1.1 定义 timing authority、sync quality、execution mode 和 authoritative joint eligibility 的统一运行时模型，并覆盖 `source_pts`、`legacy_nominal_fps`、`missing` 与结构化 reason code。
- [x] 1.2 实现 structural authority validation 与 quality gate 的组合 resolver：先校验 schema/camera/mapping/数值，再执行 `good / degraded / unknown / unavailable` 决策。
- [x] 1.3 为 authority matrix 编写单元测试，验证 good → `joint_authoritative`、degraded → `joint_degraded`、unknown/unavailable → `single_view_fallback`，并验证 nominal timing 不具备 authoritative eligibility。

## 2. Registered video PTS sidecar

- [x] 2.1 在最终 registered video 完成登记后接入 PTS sidecar materialization，复用原子临时文件 + `os.replace()` 写入策略。
- [x] 2.2 保存 sidecar provenance、frame count、FPS、首尾 PTS 和生成失败 reason；sidecar 失败不得回滚 CaptureTake 或删除原始 TS/registered video。
- [x] 2.3 为 sidecar 缺失、损坏、空文件、非单调 frame index/PTS 增加测试，并确认单摄 legacy 仍可使用 nominal FPS fallback。
- [x] 2.4 为 joint authoritative 分析增加 sidecar readiness 检查，确保两路 timing authority 均为 `source_pts` 才能进入 authoritative eligibility。

## 3. Frame selection 与 canonical clock

- [x] 3.1 修改 frame selection，在 `map_reference_time()` 前执行 `valid_start_seconds / valid_end_seconds` gate，并区分 `unavailable_no_sync`、`unavailable_outside_valid_interval`、`unavailable_out_of_media_range` 和 `unavailable_selection_error`。
- [x] 3.2 保持 source-frame 单调不重复消费，补充细分 status 与 mapping diagnostics 的计数和 reason 传递，不改变 `no_new_frame` 的 tracker 不重复更新语义。
- [x] 3.3 让每路 `FrameSample`/等价 timing context 携带 source timestamp、mapped take timestamp、selection error、timing authority 和 sync quality。
- [x] 3.4 为有效区间边界、媒体首尾越界、误差超限、重复 source frame 和 PTS drift 编写 clock/frame-map 回归测试。

## 4. Joint executor 与 artifact provenance

- [x] 4.1 让 `MultiViewJointExecutor` 为每个 view 使用自己的 timing provider，并在执行前消费 authority resolver；不得再只依据 `validate_sync_authority().valid` 进入 synchronized joint。
- [x] 4.2 将实际 execution mode、authoritative eligibility、authority reason、每路 timing provenance 和 frame status counters 写入 joint diagnostics 与 job result。
- [x] 4.3 将 FrameSample timing context 贯穿 `JointViewRuntime`、`ViewFrameResult`、joint observation adapter 和 `fused_player_trajectory.v2` 的 `view_observations`。
- [x] 4.4 保持历史 v1/v2 artifact reader 兼容，并为新 authoritative run 增加 required timing fields 的完整性校验。
- [x] 4.5 增加 executor fallback 测试：good、degraded、unknown、missing sidecar、missing secondary mapping 和 out-of-range tick 均产生正确 mode/message/diagnostics。

## 5. 验证与交付

- [x] 5.1 更新现有双摄 sync、clock、reliability 和 real-capture smoke tests，确保新增 status、authority 和 provenance 不破坏历史兼容行为。
- [x] 5.2 增加 synthetic dual-camera fixture，覆盖不同 FPS、source PTS 偏移/漂移、分段 valid interval、selection error 和 secondary unavailable。
- [x] 5.3 在真实 CaptureTake 上验证最终 registered video sidecar、两路 timing authority、canonical tick 配对和 diagnostics 可回放；记录 degraded/unknown 样本但不纳入 authoritative cohort。
- [x] 5.4 运行 backend 相关测试与 OpenSpec 校验，确认 P1-A 可以仅依赖本 Change 输出的可信 FrameSample/timing contract。
