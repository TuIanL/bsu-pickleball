## 1. 输入契约与基础类型

- [x] 1.1 定义 `FramePairingPlan`、per-tick pairing decision 和 status 枚举，包含 reference/secondary frame、时间戳、映射误差和 unavailable reason。
- [x] 1.2 扩展多视角 Parent/view input 持久化字段，保存真实 `camera_id` 和 `canonicalFrameId`，兼容历史任务缺省值。
- [x] 1.3 实现共享 `SyncAuthorityValidator`，校验 schema、reference camera、required secondary mapping、camera identity、数值范围、quality 和 valid range。
- [x] 1.4 为 validator 和 pairing plan 定义结构化错误/诊断模型，避免继续通过异常字符串或 mapping 猜测传递原因。

## 2. 权威帧配对与融合接线

- [x] 2.1 实现基于 reference observations、secondary frame timings 和 sync mapping 的一次性 `FramePairingPlan` 构建器。
- [x] 2.2 重构 late-fusion association pass，使每个 tick 只读取 pairing plan 指定的 secondary source frame 上的全部球员观测。
- [x] 2.3 重构 `CanonicalTimelineBuilder` 和 fusion pipeline，消费同一 pairing plan，删除重复 nearest frame selection 逻辑。
- [x] 2.4 保证 pairing plan 的 source frame index 单调/可追溯，并将 selection error、unavailable reason 写入融合诊断。
- [x] 2.5 将严格 sync authority validator 接入 coordinator preflight、late executor 和 joint executor，移除 secondary mapping 猜测路径。

## 3. 真实模式与结果诊断

- [x] 3.1 在 fused diagnostics 中统计 `secondary_available_samples`、`dual_evidence_samples`、`single_view_fallback_samples`、`predicted_samples` 和 `effective_multiview_ratio`。
- [x] 3.2 实现 effective mode 判定：零双摄证据为 `single_view_fallback`，低覆盖为 `multiview_degraded`，正常覆盖才为 `multiview_fused`。
- [x] 3.3 修改 `MultiViewResultComposer`，使 manifest、Parent result、message 和 diagnostics 使用一致的 effective mode 与 fallback reason。
- [x] 3.4 保留 `fusion_performed` 作为技术执行事实，不再用它直接推导用户可见的多视角模式。

## 4. Canonical frame wiring

- [x] 4.1 在 CaptureTake/分析协调层实现 canonical frame 的 write-once 创建、加载和同 take 复用。
- [x] 4.2 在新请求 preflight 中校验已存在 canonical frame 与本次 endpoint/orientation 定义一致；冲突时结构化拒绝，不自动翻转。
- [x] 4.3 将 canonical frame reference 传入并持久化到 `MultiViewFusionRun` 和 `MultiViewJointRun`，并回显到 artifact/diagnostics。
- [x] 4.4 为历史已完成任务保留只读兼容路径，不重写既有单摄或 fused artifact。

## 5. 执行模式与前端协议

- [x] 5.1 统一 `multiview.executionMode` 为双摄创建请求规范字段，统一 Parent 持久化字段为 `executionMode`，明确旧 `multiviewExecutionMode` 仅为历史文档名。
- [x] 5.2 让前端创建请求支持显式发送 `late_fusion_v1` 或 `joint_tracking_v2`；在真实 A/B 验收前保持默认值为 `late_fusion_v1`。
- [x] 5.3 确认两种执行模式都进入 input/config signature，并可在同一 CaptureTake 上独立创建、运行和读取结果。
- [x] 5.4 在 Parent summary、manifest 和详情页暴露 requested mode 与 effective mode，避免用户混淆执行路径和最终证据质量。

## 6. 测试与验收

- [x] 6.1 添加 adversarial pairing 测试：容差窗口包含多帧、多球员时，association 与 fusion 必须使用同一 source frame，且不得出现跨帧球员混配。
- [x] 6.2 添加 sync authority 测试：缺 secondary mapping、错误 camera identity、非法 schema/rate/quality 均进入可解释 fallback 或拒绝。
- [x] 6.3 添加零副摄证据、低覆盖和 prediction-only 场景的 Composer/manifest/effective mode 测试。
- [x] 6.4 添加同一 take 多次分析和 late/joint A/B 的 canonical frame id 复用测试。
- [x] 6.5 添加前端请求协议测试，确认显式 `multiview.executionMode` 不会被后端静默丢弃，并验证历史缺省仍为 late-fusion。
- [x] 6.6 使用真实双摄 CaptureTake 完成 late-fusion 与 joint-tracking smoke test，核对 pairing diagnostics、effective mode、artifact 归属和 A/B 输入签名。
- [x] 6.7 记录并创建独立的 PTS 时间基准迁移 Change，明确本 Change 不以 nominal `frame_index / fps` 替代 source PTS 作为完成条件。
