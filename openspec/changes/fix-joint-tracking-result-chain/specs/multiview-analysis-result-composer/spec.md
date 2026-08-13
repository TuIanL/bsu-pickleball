## ADDED Requirements

### Requirement: fused 样本时间戳契约

fused trajectory v2 样本 SHALL 携带可计算的 `timestamp_seconds`（由 `take_timestamp_ms` 派生，单位秒）。Composer 消费 fused 样本计算位置类指标与生成 tracks 时 SHALL 使用该时间戳，MUST NOT 使用默认 0.0。

#### Scenario: 指标时间戳正确

- **WHEN** Composer 重算速度/厨房停留指标
- **THEN** 速度与停留 SHALL 基于真实样本时间差计算
- **AND** 不得因时间戳缺失输出全 0 指标

#### Scenario: 前端小地图时间过滤恢复

- **WHEN** 前端按播放时间窗口过滤轨迹点
- **THEN** 轨迹点 SHALL 落在正确时间窗口内
- **AND** 播放超过 3 秒后小地图 SHALL 仍显示轨迹

### Requirement: joint compose 视觉层产物契约

joint_tracking_v2 模式的 `compose_joint_result` SHALL 产出或继承前端视觉层产物（tracking_overlay / pose_overlay / heatmaps / player_render_trajectory 等），并补齐 `*_url` / `*_status` / `*_detail` 契约，使前端框架、骨架、热力图与小地图可用。

#### Scenario: joint 结果含视觉层产物

- **WHEN** joint Parent 完成分析
- **THEN** Parent artifacts SHALL 包含 `tracking_overlay_url`、`pose_overlay_url`、`heatmaps_url` 等
- **AND** 前端视觉层 SHALL 可加载（非 unavailable）

#### Scenario: 产物来源如实标注

- **WHEN** joint 模式产出视觉层产物
- **THEN** 产物 SHALL 标注来源（joint run / `GlobalPlayer` 标签）
- **AND** SHALL NOT 伪装为 child 单摄产物

### Requirement: 聚合 stage 状态来源修正

聚合 stage（`_build_aggregate_stages`）的 A/B 机位状态在 joint 模式 SHALL 使用真实执行结论（joint run 完成即视为 A/B 成功），MUST NOT 依赖创建后不再更新的 `viewRuns` 状态，避免误报"A/B 机位分析失败"。

#### Scenario: joint 完成不误报失败

- **WHEN** joint run 成功完成
- **THEN** 聚合 stage 的 `multiview-view-a` / `multiview-view-b` SHALL 为 done
- **AND** 不得显示 failed（即使 `viewRuns` 仍停在 queued）
