# A/B 验证流程（multiview-player-trajectory-fusion）

> 目标：证明 Fusion 相对最佳/默认单视角确实提升球场位置质量，而不是"两个轨迹被合到了一起"。

## 对比组

```text
A: single cam_1
B: single cam_2
C: configured default view   （产品默认选用的单视角，如 cam_1）
D: multiview fused
```

不使用事后 oracle baseline（"每帧知道哪个 camera 更准后再选 best"过强且不真实）。

## Ground Truth 规范（`multiview_gt.v1`）

```json
{
  "schema_version": "multiview_gt.v1",
  "source": "manual_labeling",
  "players": [{ "global_player_id": "g1" }],
  "samples": [
    {
      "global_player_id": "g1",
      "take_timestamp_ms": 1000,
      "x_ft": 5.0,
      "y_ft": 8.0,
      "source": "manual",
      "cross_checked": true,
      "near_court_line": true
    }
  ]
}
```

**GT 独立性约束（避免循环验证）：**
1. GT court coordinate **不依赖被评估的同一套 Homography**——不采用"人工点图像脚点 → 用当前 Homography 投影当 GT → 再评价该 Homography"。
2. P0 采用有限成本独立方案：抽选**已知球场线附近帧** + 人工确认物理 court coordinate + **两视角交叉复核**。
3. GT 每个 sample 带 `global_player_id`，使 identity switch 可统计。

## 指标（`scripts/multiview_ab_validate.py`）

```text
球场位置 RMSE / mean / median error
轨迹缺失率（GT 未覆盖比例）
异常跳点率（帧间速度 > 阈值）
跨视角冲突率（fused 的 conflict 样本占比）
identity association switch count
连续轨迹覆盖率
```

分**区域**统计：`overall / far-side subset / near-side subset`（`--far-y-ft` 分界），重点验证：

```text
Cam1 far-side（cam_1 远端）  → 单视角差，fused 应有提升
Cam2 far-side（cam_2 远端）  → 单视角差，fused 应有提升
overall
```

这正是"双摄互补"最直接的证据。

## 判定

- fused 的 `overall RMSE < 最佳单视角`，且 `far-side` 提升显著（否则双摄互补价值存疑）；
- fused `coverage >= 最佳单视角`（不能以牺牲覆盖换精度）；
- fused `identity switch count` 不劣于单视角；
- fused `jump rate` 不高于单视角（不能引入新抖动）。

## 运行

```bash
PYTHONPATH=. .venv/bin/python scripts/multiview_ab_validate.py \
  --gt data/gt/take_1_gt.json \
  --cam1 data/outputs/<cam1>/player_render_trajectory.json --cam1-orientation mirror_y \
  --cam2 data/outputs/<cam2>/player_render_trajectory.json --cam2-orientation mirror_x \
  --fused data/<take>/analysis/multiview/<run>/fused_player_trajectory.json \
  --output /tmp/ab_report.json
```

## 结论模板

| 指标 | cam_1 | cam_2 | default | fused | 判定 |
|------|-------|-------|---------|-------|------|
| overall RMSE (ft) | | | | | fused < best single |
| far-side RMSE (ft) | | | | | 提升显著 |
| coverage | | | | | fused ≥ best single |
| jump rate | | | | | fused ≤ best single |
| identity switch | | | | | fused 不劣 |

**结论（待真实数据填充）**：___
