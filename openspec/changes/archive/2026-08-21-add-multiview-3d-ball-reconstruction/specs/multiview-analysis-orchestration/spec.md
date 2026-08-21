## ADDED Requirements

### Requirement: joint 执行新增球立体兄弟路径
系统 SHALL 使 joint 分析执行在既有 fused player 输出之外，增加一条球 stereo 兄弟路径：为每个 canonical tick 驱动双视角球检测/关联/三角测量，并纳入联合产物链。

#### Scenario: 双视角球证据驱动
- **WHEN** joint 执行进入某 canonical tick
- **THEN** 系统 SHALL 在每视角仅消费 `frame_status == "available"` 的真实源帧上运行球检测/关联/三角测量
- **AND** 通过 `CanonicalAnalysisClock` 的同步映射保证 Cam1/Cam2 在同一 canonical 时间参考系
- **AND** `available_extrapolated` 帧 SHALL 不进入球链

#### Scenario: 与 fused player 输出并存
- **WHEN** joint 执行完成
- **THEN** 球 stereo evidence（`multiview_ball_stereo_evidence.v1`）与 v3 用户轨迹 SHALL 作为新增连接产物，与既有 fused player 产物并存产出
- **AND** 球链失败 SHALL NOT 破坏 fused player 产物