## Context

当前系统已经具备 `FrameTimingProvider`、PTS sidecar、`SyncCalibration`、`CanonicalAnalysisClock` 和 `evaluate_sync_gate()`。但执行路径仍把几个不同语义混在一起：结构校验通过不等于同步质量足够，缺少 sidecar 时的 nominal FPS fallback 也不等于 authoritative timing；`valid_start_seconds / valid_end_seconds` 已被保存，却没有参与实际 frame selection。

本 Change 是 P1 recovery 的前置边界。它需要覆盖 CaptureTake 完成后的最终注册视频、canonical tick、joint observation 和 v2 artifact，但不改变录制终态、原始 TS 保留或 P1 recovery 算法。

## Goals / Non-Goals

**Goals:**

- 将 timing authority 统一表达为 source PTS、legacy nominal FPS、missing，并允许调用场景选择不同的 fallback policy。
- 让 structural authority validation 与 sync quality gate 在执行器中按固定顺序生效。
- 对最终注册分析视频物化并验证 PTS sidecar，同时保留录制成功与 timing 不可用的独立状态。
- 让 calibration valid interval 和 selection error 真正决定每个 canonical tick 的 view status。
- 保留每路 source timing、mapped take timing、selection error、timing authority 和 sync quality，直到 joint observation 与 v2 artifact。
- 为 joint、degraded、compatibility 和 single-view fallback 提供可校验的 diagnostics。

**Non-Goals:**

- 不修改 RTSP/FFmpeg 录制控制、CaptureTake 终态化或 MP4 合并失败恢复。
- 不实现内容同步锚点采集、硬件同步、Genlock 或新的漂移拟合算法。
- 不实现 cross-view guidance、binding aging、local identity recovery 或 P1 recovery KPI。
- 不删除历史 artifact，也不禁止单摄历史任务使用 nominal FPS compatibility fallback。

## Decisions

### 1. 两阶段 authority 决策

执行器先调用 structural validation，确认 schema、camera identity、数值范围、当前 secondary mapping 和有效时间范围可解析；只有结构合法后，才调用 quality gate 计算 `good / degraded / unknown`。

最终决策至少包含：

```text
structural_valid
timing_authority_by_view
sync_quality
execution_mode
authoritative_joint_eligible
reason_codes
```

`validate_sync_authority().valid` 不再直接作为 synchronized joint 的准入条件。quality gate 负责区分 `good → joint_authoritative`、`degraded → joint_degraded`、`unknown/unavailable → single_view_fallback`；任一路 timing authority 不是 source PTS 时，joint 最多进入 compatibility/degraded，不能声明 authoritative。

选择组合决策而不是只扩展 `validate_sync_authority()`，是因为结构错误与质量降级的恢复策略不同：结构错误应阻止错误映射继续传播，质量降级则允许运行并保留实验诊断。

### 2. 在最终注册视频边界生成 PTS sidecar

sidecar 绑定最终用于分析的 registered video，而不是只绑定原始 fragment。视频登记完成后，异步或同步调用 `write_frame_timing_sidecar()`，使用临时文件和原子替换写入 `<media>.pts.jsonl`，随后由 `FrameTimingProvider.from_media()` 校验。

sidecar 生成失败不回滚 CaptureTake，也不删除视频；对应 CaptureTrack 标记 `timing_authority=unavailable` 和结构化 reason。单摄 legacy 与 compatibility 路径仍可使用 nominal provider，但新 joint authoritative run 必须显式拒绝该资格。

### 3. Frame selection 先做 calibration interval gate

对每个 reference target time，selection 顺序固定为：

```text
timing authority / sync mapping available
    ↓
reference time within calibration valid interval
    ↓
map_reference_time()
    ↓
target within secondary media range
    ↓
nearest source frame
    ↓
selection error tolerance
    ↓
monotonic / no_new_frame check
```

`FrameSelection` 和 `SynchronizedFrameBundle.frame_status` 使用可解释状态：`available`、`unavailable_no_sync`、`unavailable_outside_valid_interval`、`unavailable_out_of_media_range`、`unavailable_selection_error`、`no_new_frame`。状态不得通过默认 offset=0 或 nominal frame index 猜测恢复。

### 4. 以 FrameSample 作为唯一 timing provenance 载体

不重新设计时间模型。`FrameSample` 已经包含 source frame、source timestamp、mapped take timestamp 和 selection error；joint runtime 需要把该对象或等价 immutable timing context 传给 tracking result，再由 observation adapter 写入 `JointObservation` / `JointViewObservation`。

每路 observation 至少保留：

```text
source_frame_index
source_timestamp_ms
mapped_take_timestamp_ms
selection_error_ms
timing_authority
sync_quality
```

历史 v1/v2 reader 对缺失字段使用兼容默认值；新 authoritative run 不允许缺失这些字段后仍通过 eligibility。

### 5. 运行模式与统计分层

采用以下矩阵：

| 条件 | 运行模式 | authoritative joint | P1 primary cohort |
| --- | --- | --- | --- |
| 两路 source PTS + sync good | `joint_authoritative` | 是 | 纳入 |
| 两路 source PTS + sync degraded | `joint_degraded` | 否 | 排除，进入 sensitivity |
| 任一路 nominal fallback | `compatibility_degraded` | 否 | 排除 |
| sync unknown/unavailable 或 mapping 缺失 | `single_view_fallback` | 否 | 排除 |

这样 degraded 素材仍可用于鲁棒性分析，但不会与 good 素材合并为一个 P1 recovery recall。

### 6. 向后兼容与边界

单摄任务继续允许 nominal FPS；late-fusion 兼容路径可以运行 nominal 或 degraded，但必须在诊断中暴露 authority。只有 `joint_tracking_v2` 的 authoritative eligibility 收紧。原始 TS、registered MP4 和历史 artifact 的路径不变。

## Risks / Trade-offs

- [Sidecar 生成增加 CaptureTake 完成耗时或磁盘占用] → 只写紧凑 JSONL，使用原子写入；生成失败不影响视频播放和录制完成。
- [旧素材没有 sidecar，joint 任务可运行数量下降] → 保留 compatibility/degraded 路径，但禁止其进入 authoritative 结果和 P1 主实验。
- [严格 valid interval 导致首尾 tick 变为 unavailable] → 暴露精确 reason，并允许下游按既有 sample-level fallback 处理。
- [仅有每路 local PTS 仍不足以证明跨摄同步] → `source_pts` 只表示每路 timing authority；跨路可信度仍由 content anchor calibration 的 quality 决定。
- [新增 artifact 字段影响历史 reader] → 新字段保持 additive，历史 artifact 使用兼容默认值，新运行在 authoritative gate 中强制检查字段完整性。
- [执行器同时处理 structural invalid 与 quality degraded 时语义复杂] → 固定两阶段决策顺序，并用 authority matrix 覆盖每种组合。

## Migration Plan

1. 先实现 sidecar materialization、provider provenance 和 valid interval/frame status，不改变旧单摄路径。
2. 增加 authority resolver，将 structural validation 与 quality gate 接入 joint executor，并输出 execution mode/reason。
3. 将 timing context 贯穿 clock、runtime、observation adapter 和 v2 artifact。
4. 对历史素材保持 compatibility fallback；对新 joint authoritative run 启用严格 eligibility。
5. 通过单元测试、synthetic timing fixture、真实双摄 smoke 和旧 artifact reader 回归后，再将 P1 recovery 作为下游 Change 接入。

回滚时可关闭 authoritative joint eligibility，保留 sidecar 和 diagnostics；不得删除已生成的 sidecar、原始视频或历史 artifact。

## Open Questions

- sidecar 生成是 CaptureTake 完成流程中的同步步骤，还是由后台 materialization job 异步执行；两者都必须在分析入口前提供明确的 `pending/unavailable/ready` 状态。
- `max_pairing_error_ms` 是否按 source FPS 动态计算，还是继续使用统一配置阈值；本 Change 只要求语义一致，不重新调整实验参数。
- 多于两路时，`FrameSample` 和 authority resolver 是否直接泛化为 view map；当前实现仍以双摄为最小闭环。
