# 真实数据验收记录

日期：2026-08-25

## 样例与场景资产

- `capture_take_id`: `ct_6949bef776a5`
- 同步录制：`sync_20260720_122645_317228`
- 双摄视频：`rec-126e7bdd17`（cam_1）和 `rec-e5105932b0`（cam_2）
- 图像尺寸：两路均为 `1920×1080`
- 最新场景 revision：`6`，状态 `ready`，provenance `manual_verified`
- 标准球网 profile：两端 `3.0 ft`（91.44 cm），中心 `2.833333 ft`（86.36 cm）
- 两路均保存了左端、中心、右端人工标注；当前 revision 没有独立 hold-out 图像点，场景质量中的 residual、hold-out 和 height uncertainty 仍为空。

## 静态 A/B

旧方案使用任务 `job-153abf7b60`，显式 approximate、无 scene revision：

- stereo measurements：4
- stereo coverage：0.111
- trajectory：`PARTIAL_3D`
- measurement source/validity：旧 artifact 未保存
- estimated z：`-0.439–-0.351 ft`，说明旧近似路径存在负高度/退化问题。

net-assisted 方案使用任务 `job-a0118baff4`，引用 scene revision `4`：

- stereo measurements：452
- stereo coverage：1.0
- camera model source：`net_refined_virtual`
- metric validity：`approximate_multiview`
- estimated z：`0.223–4.420 ft`
- depth valid：452/452
- ray angle：`10.041–170.193°`，均值 `108.904°`
- cam_1 reprojection：均值 `7.470 px`
- cam_2 reprojection：均值 `7.216 px`
- height uncertainty：未提供

对最新 revision `6` 直接重算 refinement 得到：

- cam_1：court `1.067 px`，net `3.761 px`
- cam_2：court `3.241 px`，net `8.433 px`
- 两路均使用 normalized DLT fallback，`metric_qualified=false`
- hold-out residual 和 height uncertainty：未提供

结论：球网辅助相机确实被接入，但当前真实镜头仍只能发布 approximate 3D，不能宣称严格 metric 高度。

## 场景复用与回滚

- 当前 metric job 的两路 `jointViewInputs` 均引用同一个 `capture_take_id` 和 scene revision `6`，没有为每个视频复制 scene asset。
- 同一采集任务保留 revisions `1–6`，历史任务 `job-153abf7b60` 的 approximate artifact 和 `job-a0118baff4`/`job-0bb3c7e440` 的 net-assisted artifact 均可读取。
- 对 metric 模式缺少 revision 的实际 API 预检返回 HTTP `400`：`metric scene calibration revision required`，没有创建任务。
- 针对 scene/artifact/fallback 的回归测试通过；本轮相关测试为 `20 passed`。

## 动态球路

`job-a0118baff4` 的动态产物：

- 轨迹段：91
- 网附近样本：95
- 双摄 evidence：`FULL_ESTIMATED_3D`
- 段级结果：88 段 `visualization_only`，3 段 `unavailable`
- speed eligibility：91/91 为 `false`
- peak-height eligibility：91/91 为 `false`
- 47 个 `y=22 ft` 穿越候选中存在明显跨段跳变，当前不能把它们认定为可靠穿网事件。

结论：approximate fallback 语义和指标降级正确生效；真实视频尚未提供可用于验收的可靠穿网事件，因此不能把动态验收全部标记为通过。

## 本轮状态

- 已确认：场景复用、历史 artifact 保留、metric 缺失 revision 的回滚/拒绝路径。
- 部分确认：静态 A/B、动态 approximate fallback。
- 尚未完成：独立 hold-out 点、完整 residual/不确定度落盘、可靠穿网事件验收。

## 2026-08-26：revision 7 hold-out 验收补充

### 样例和静态标定

- 新任务：`job-905a365b09`，同一 `capture_take_id` `ct_6949bef776a5`，窗口 `0–60 s`。
- 新发布的 scene revision：`7`，状态 `ready`，两路均为 `1920×1080`。
- revision 7 已保存两路人工 `left / center / right` 标注，以及 `holdout_left_quarter`（`x=5 ft`）和 `holdout_right_quarter`（`x=15 ft`）的 image-space 与 canonical 3D 坐标；标准 profile 两个 hold-out 高度均为 `2.875 ft`（约 `87.63 cm`）。

静态 A/B 使用同一份 revision 7、两路球场角点和当前代码直接重算。数值为每视角平均像素误差：

| 视角 | Homography baseline court / net / hold-out | Net-assisted court / net / hold-out | 结论 |
| --- | --- | --- | --- |
| cam_1 | `~0.00 / 306.73 / 235.58 px` | `1.50 / 3.64 / 12.89 px` | 非共面球网约束显著降低 net residual；hold-out 略高于 `12 px` 门槛。 |
| cam_2 | `~0.00 / 346.91 / 268.40 px` | `4.29 / 11.54 / 17.98 px` | 相比 baseline 有明显改善，但 net 与 hold-out 均未过门。 |

- 动态 evidence 中的 ray angle 为 `7.953–170.254°`（均值 `107.477°`），`447/447` measurement depth valid。
- 两路都落入 `normalized_dlt_fallback`，因此 `height_uncertainty_ft = Infinity`、`metric_qualified = false`；当前结论仍是 `approximate_multiview`，不得发布 metric 高度或高度指标。
- 校验中发现旧 worker 对 hold-out 字段没有热重载，且 legacy endpoint swap 没有同步翻转四分之一点。前者已通过重启 local runtime 解决；后者已修复并增加回归测试。修复后 cam_2 hold-out residual 从错误的 `695.29 px` 降为 `17.98 px`，但仍真实地未达标。

### 动态球路（待新 worker 重跑最终确认）

`job-905a365b09` 的旧 worker artifact 仍可用于验证降级语义：

- 447 个 stereo measurement，全部为 `net_refined_virtual + approximate_multiview`，无 high-quality metric anchor。
- 91 个轨迹段：58 个 `stereo_estimated_3d`（approximate）、32 个 visualization-only、1 个 unavailable；speed 与 peak-height eligibility 均为 `0`。
- 以 `y=22 ft` 相邻样本插值得到 30 个穿网候选（21 个段），其中 2 个低于网顶、7 个段出现重复穿越候选，不能宣称为可靠穿网事件。

由于 `job-905a365b09` 在重启前的 external worker 中执行，artifact 还写入了过时的 `holdout_control_points_missing`。需要在已重启 worker 上使用 revision 7 再运行一次同窗口任务，确认 artifact 实际写入 hold-out residual（而不是缺失）后，才能完成动态任务 7.4 的最终验收。

## 2026-08-26：已重启 worker 的最终动态验收

- 新任务：`job-4d268895f7`，窗口 `0–30 s`，引用同一 `capture_take_id` 的 `scene revision 13`，输入模式为 `metric`、状态为 `ready`。
- 正式 stereo evidence 已保存两路相机诊断，且 `holdout_control_points_missing` 为 `0`：cam_1 的 court / net / hold-out residual 为 `1.50 / 3.64 / 12.89 px`；cam_2 为 `3.63 / 9.57 / 17.35 px`。cam_2 同时明确记录 `endpoint_swapped_legacy_compat`，说明四分之一点已与端点一同翻转并参与验收。
- 两路仍使用 `net_refined_virtual + normalized_dlt_fallback`，相机质量分别为 `degraded`、`invalidated`；hold-out / net residual 和无限高度不确定度未达 metric 门槛。因此有效场景状态为 `degraded`，该任务没有错误地把结果发布为 metric。
- 动态证据共 `158` 个双摄 measurement，全部 depth valid，ray angle 为 `14.999–164.826°`（均值 `115.282°`），网附近（`|y-22|<1 ft`）样本 `40` 个，high-quality metric anchor 为 `0`。
- 共 `38` 个轨迹段：`16` 个 `stereo_estimated_3d + approximate_multiview`、`21` 个 visualization-only、`1` 个 unavailable；speed 和 peak-height eligibility 均为 `0`，原因明确为 `approximate_multiview_not_metric_eligible`。
- 以相邻样本穿越 `y=22 ft` 且时间差不超过 `150 ms` 的方式筛查，得到 `11` 个候选（`7` 个段）。其中 `9` 个高于网顶、`2` 个低于网顶，且 `flight-9`、`flight-19` 出现重复候选；它们仅作为 approximate 轨迹诊断，**不**认定为可靠穿网/触网事件。

结论：动态球网附近高度、3D 段状态和指标资格均已在真实任务上核验；hold-out 诊断传播和 legacy 翻转修复已生效。真实镜头的 residual 仍未达到 metric 门槛，系统按设计安全输出 `approximate_multiview` 和 visualization-only，而没有生成不可信的球速、最高点或穿网结论。
