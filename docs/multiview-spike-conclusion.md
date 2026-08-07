# P0 Spike 验证结论（multiview-player-trajectory-fusion）

> 状态：**部分验证**。数据源契约、adapter 与 canonical timeline 已端到端跑通；
> 三个核心假设 (a)(b)(c) 的**完整量化确认需要真实双摄 take**（含 `sync_calibration.json`）。

## 已验证（代码层，自动化测试覆盖）

1. **数据源契约冻结**：`player_render_trajectory.json` 的 `schema_version = player-render-trajectory.v2`；
   sample `source ∈ {"observed", "interpolated"}`（**不是 "detector"/"detected"**）；无 `bbox` 字段；
   `x_ft/y_ft` 为 raw（未平滑）。实测 `job-5c706a00ad`：observed=546 / interpolated=2299，`projection_confidence=0.7`。
2. **Spike Adapter**：过滤 `source == "observed"` 正确；冒烟断言"至少一个 observed"生效
   （全被滤光时抛 `SpikeAdapterError`）；canonical 归一化（mirror_y/mirror_x 等）正确。
3. **Canonical Timeline 契约**：无 sync authority 时副视角**一律 unavailable**（拒绝假配对，
   这正是 job-level 完整性所要求的）；有 sync mapping 时按 `abs(selection_error_ms) <= max_pairing_error_ms`
   配对，越界标记 unavailable。
4. **端到端脚本** `scripts/multiview_spike_validate.py` 可在真实 artifact 上运行并产出报告。

## 真实双摄 take 上的实测输出（占位，待补）

在 `job-5c706a00ad` 与 `job-3a91cd44ed` 两个非双摄对 artifact 上运行：

```json
{
  "sync_available": false,
  "canonical_ticks": 546,
  "dual_observed_ticks": 0,
  "hypothesis_a": { "paired_count": 0 },
  "hypothesis_c_proxy": { "ref_mean_proj_conf": 0.70, "sec_mean_proj_conf": 0.70 }
}
```

`dual_observed_ticks = 0` 是**符合契约的结果**：无权威 sync 时禁止假配对。
（这两个文件也不是同一 take 的双摄对。）

## 三个假设的验证方法（待真实数据执行）

| 假设 | 方法 | 判定 |
|------|------|------|
| (a) 同一球员两路 canonical 化后空间接近 | 同一真实 take 的两路 render artifact + `sync_calibration.json`，跑 `multiview_spike_validate.py`，按 player 拆分后看 canonical 配对距离中位数 | `median < ~2 ft` 且显著小于未归一化时 |
| (b) 关联稳定 | 对每个 reference player 做时间窗 best-match 计数（Phase 4 关联器落地后闭环） | best-match 翻转次数少 |
| (c) 近端机位改善远端轨迹 | 近端机位 vs 远端机位的投影置信度/观测密度 + Phase 9 人工 GT 的 RMSE 对比 | fused RMSE < 最佳单视角 |

## 需要的真实数据（阻塞项）

- 一个**同一 take、两个机位**均已分析出 render trajectory 的双摄 take；
- 该 take 的权威 `dual_camera_sync_calibration.v1` 落在 `timeline/sync_calibration.json`；
- 每路已配置 `court_orientation`（对向底线机位：`cam_1 ≈ mirror_y`、`cam_2 ≈ mirror_x`，以实际摆位为准）。

有数据后：`python scripts/multiview_spike_validate.py --reference-artifact <cam1> --secondary-artifact <cam2> --reference-orientation mirror_y --secondary-orientation mirror_x --sync-calibration <take>/timeline/sync_calibration.json --output /tmp/spike_report.json`

## 下一步

- Phase 4 `CrossViewPlayerAssociator` 落地后，脚本增加按 player 的稳定关联统计；
- Phase 9 A/B 用人工 GT 完成假设 (c) 与整体精度提升的量化证明。
