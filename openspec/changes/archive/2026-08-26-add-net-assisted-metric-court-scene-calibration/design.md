## Context

当前项目使用球场四角标定得到每个视角的球场平面 Homography，并通过 `virtual_camera` 在假设内参下构造近似 pinhole 相机。双摄球路链路已经能够进行逐 tick 三角测量和整段 3D 曲线重建，但相机模型的 Z 轴约束仍主要来自平面标定和先验假设，因而需要把高度结果明确标记为 approximate。

本变更把球网视为一个静态、已知几何的非共面标定物。以 `capture_take_id` 为场景标定边界：同一场比赛/采集任务中的多个录制视频和视角默认使用固定的摄像机位置、角度和镜头设置，并共享同一份场景标定 revision。系统不做逐帧动态重标定；当采集配置不再属于同一固定机位时，创建新的 revision。

首版的球网观测方式是人工标注和手动微调。数据模型同时保存 annotation provenance，允许未来接入球网自动建议模型，自动建议必须经过人工确认后才能进入 `ready` 场景标定。

## Goals / Non-Goals

**Goals:**

- 建立采集任务级、可追溯、可复用的 `metric_court_scene.v1` 场景标定资产。
- 以现有 Canonical Court Frame 为统一世界坐标系，把球场地面点和球网非共面点共同用于相机 refinement。
- 支持球网两端 91.44 cm、中心 86.36 cm 的标准顶部 profile，并支持现场实测 profile。
- 让双摄球路、球员空间分析和 Three.js 场景消费同一份场景模型、相机 revision 和质量诊断。
- 在场景标定缺失或质量不足时安全降级到现有 approximate 3D/2.5D 路径，禁止把近似结果标为 metric。
- 传播场景标定质量、回投误差、射线几何质量和高度不确定度，为高度指标设置独立资格。

**Non-Goals:**

- 不在本变更中搜集公开数据集、训练球网识别模型或上线自动标注闭环。
- 不做密集环境点云、NeRF 或一般性摄影测量网格；第一版只建立参数化球场、球网和相机模型。
- 不改变现有双摄同步、Canonical Timeline、球员身份或球路分段语义。
- 不在首版引入径向畸变优化；沿用现有零畸变 approximate 相机假设，并把残差作为诊断。
- 不把摄像机移动作为正常输入处理，也不通过逐帧重估相机姿态来掩盖采集配置变化。

## Decisions

### 1. 场景标定以 CaptureTake 为边界，按 revision 发布

场景标定资产归属于 `capture_take_id`，而不是某个单独 AnalysisJob。Parent、child 或 joint analysis job 只引用场景标定 revision，不复制其内容。这样同一场比赛的多个录制视频可以共享相同的摄像机和球场几何，同时保证重跑任务仍然可复现。

建议资产至少包含：

```text
metric_court_scene.v1
├── capture_take_id
├── revision / status
├── canonical_frame_id
├── coordinate_units
├── court_geometry
├── net_model
│   ├── profile_type
│   ├── control_points_3d
│   └── height_source
├── views[]
│   ├── view_id / camera_id / video_id
│   ├── calibration_id / image_size
│   ├── image_annotations
│   ├── camera_model
│   └── quality
└── provenance / timestamps
```

场景状态区分 `draft`、`ready`、`degraded` 和 `invalidated`。历史 revision 不覆盖；只有经过质量门的 revision 才能作为 authoritative scene calibration 被新任务引用。

替代方案：把球网点位写进每个 job artifact。该方案会导致同一采集任务重复标注、重跑时几何漂移，也无法表达场景资产的生命周期，因此不采用。

### 2. 球网使用参数化三维 profile，而不是单条水平线

Canonical Court Frame 继续使用现有英尺坐标：球场约为 `20 ft × 44 ft`，球网位于 `y = 22 ft`，`z` 轴垂直地面向上。首版标准 profile 使用三个核心控制点：

```text
(x=0,  y=22, z=3.0000 ft)   # 91.44 cm
(x=10, y=22, z=2.8333 ft)   # 86.36 cm
(x=20, y=22, z=3.0000 ft)   # 91.44 cm
```

顶部 profile 默认采用端点/中心约束的平滑曲线；如果人工标注了四分之一点或现场测量点，则以这些控制点拟合 profile。球网主体由顶部 profile 向下延伸到地面形成参数化 mesh，网柱位置作为独立几何实体保存。实际网柱可能超出边线，网柱坐标不强制等同于球场边线坐标。

替代方案：在前端继续使用固定高度的 BoxGeometry。该方案无法表达标准网高变化，也会使分析模型和展示模型不一致，因此不采用。

### 3. 首版人工标注，自动建议保留稳定接口

每个 view 的人工工作流使用现有球场标定的帧预览和草稿恢复能力，增加球网标注层。最小可用控制点为球网左端、中心、右端；推荐额外标注四分之一点和网柱落地点。每个点同时保存 image-space 坐标、对应的 canonical 3D 坐标、来源和人工确认状态。

数据层预留以下 provenance：

- `manual`：用户直接标注；
- `auto_suggested`：未来模型提出但尚未确认；
- `manual_verified`：用户确认或修正后的可发布点。

未来自动模型只能替换“点位建议”步骤，不能绕过现有质量门和人工确认发布 `ready` revision。首版不依赖模型文件、数据集或网络服务。

### 4. 以球场平面相机为初值，用球网非共面点做 refinement

每台摄像机先沿用现有 `inverse_homography` 和 `court_orientation` 解出 baseline virtual camera，再使用球场控制点和球网非共面控制点共同最小化回投误差，得到场景 revision 内的 `P = K[R|t]`。优化使用 robust loss，保留现有姿态消歧、相机前方性和 Canonical Court Frame 一致性检查。

首版仍使用中心主点、`fx = fy`、零径向畸变的相机假设；结果来源必须标记为 `net_refined_virtual` 或等价的 approximate/metric-qualified source，不能把它描述成未经验证的真实工厂内参。只有球场与球网 hold-out 回投、姿态、深度范围和双视角几何质量全部通过时，才把高度标记提升到 `metric_multiview`；否则保留 `approximate_multiview`。

替代方案：立即要求每台摄像机完成 checkerboard/Charuco 内参标定。该方案长期精度更高，但会增加现场操作成本，且不能替代球场坐标系和固定机位绑定，因此作为后续精度增强，不作为本变更的首版门槛。

### 5. 静态球网标定不依赖同步，动态球路继续依赖同步

球网是静态目标，两个视角可以使用不同时间抽取的标注帧；场景标定不把 frame timestamp pairing 当作必需条件。球和球员的动态三维分析仍然使用既有 `sync_calibration`、Canonical Timeline 和各自真实观测时刻回投。

场景标定资产必须保存每个 view 使用的 video/frame provenance，以便判断两个视角是否仍属于同一固定场景，但不能把静态标定点误写入动态 stereo evidence 的时间配对结果。

### 6. Metric、approximate 和 visualization-only 分层保持正交

场景标定状态、轨迹重建状态和指标资格分别记录：

- `scene_calibration_status`：`ready`、`degraded`、`unavailable` 或 `invalidated`；
- `camera_model_source`：`net_refined_virtual` 或 `homography_constrained_virtual`；
- `metric_validity`：`metric_multiview`、`approximate_multiview`、`visualization_only`、`unavailable`；
- `height_uncertainty_ft` 与其来源；
- `display_eligible`、`speed`、`peak_height`、`landing` 等独立资格。

前端可以展示 approximate 3D 球路，但不得把 approximate 高度写成精确实测值。场景标定缺失时，现有单摄/2.5D 视觉展示继续可用，并显式保留降级原因。

### 7. 在分析输入中引用 revision，而不是隐式发现

双摄 Parent 的输入和 `jointViewInputs` 增加 scene calibration reference，包括 `capture_take_id`、`revision`、适用 view ids 和场景状态。Preflight 在 metric 模式下拒绝缺少 `ready` revision 的任务；在兼容模式下允许显式选择 approximate fallback，并将选择写入 job config 和 artifact diagnostics。

这样可以避免把另一场比赛、另一套固定机位或旧分辨率的场景模型静默应用到当前视频。

## Risks / Trade-offs

- [球网边缘遮挡或标注不稳定] → 首版使用人工标注、草稿恢复、拖拽微调和质量预览；建议至少标注端点/中心，并把四分之一点作为增强质量而非隐藏必需条件。
- [标准网高与现场实际网高不一致] → 同时支持 standard profile 和 measured profile，记录高度来源；现场实测优先于默认标准值。
- [使用同一控制点拟合和验收导致过拟合] → 质量门至少包含 hold-out 网点、球场角点回投和跨视角几何检查；不得只用训练/拟合点残差发布 metric。
- [两机位视差不足导致 Z 轴病态] → 记录 ray angle、深度条件数或等价几何质量；低质量时只发布 approximate/2.5D，并保留 rejection reason。
- [固定机位假设被违反] → 同一 `capture_take_id` 内不动态重标定；当 video identity、image size、camera config 或人工确认的 setup provenance 变化时生成新 revision，禁止复用旧 revision。
- [加入场景标定后前后端字段不同步] → 新字段全部可选、revision 通过显式 reference 传递，旧 artifact 继续使用现有 virtual camera fallback，并增加 contract tests。
- [球检测和同步误差掩盖相机标定收益] → 分开记录 scene calibration residual、stereo timing quality、detector confidence 和 height uncertainty，使用静态球网 hold-out 与动态回放分别验收。

## Migration Plan

1. 新增 scene calibration artifact、revision 存储和读取 API；历史 CaptureTake 不自动回写，状态视为 `unavailable`。
2. 增加球网人工标注工作流和 standard/measured profile 序列化，先仅生成 draft/diagnostic 结果。
3. 接入 net-assisted camera refinement，建立静态样例和 hold-out 质量门；失败时自动回到现有 approximate virtual camera。
4. 将 scene calibration reference 写入双摄 Parent、joint inputs 和正式重建 artifact；旧任务使用兼容读取路径。
5. 更新双摄 stereo evidence、3D segment reconstruction 和前端场景，增加 metric/approximate/visualization-only 展示语义。
6. 在固定机位的真实采集任务上进行 A/B 回放，确认球网高度、球网附近球路、3D 轨迹和历史任务兼容性。
7. 若 net-assisted refinement 在真实数据上不稳定，通过 feature flag 或显式 fallback mode 回退到现有 approximate 路径；不删除历史 scene calibration 或 evidence artifact。

## Open Questions

- 采集任务的业务边界是否始终等同于当前 `CaptureTake`，还是需要在多个连续录制 take 之上增加一个比赛级 `camera_setup_id`。
- 网柱实际位置是否需要独立采集；首版 profile 是否将球场边线位置作为两端，还是按现场网柱中心位置建模。
- metric 模式是否只对明确选择的双摄任务开放，还是在场景 revision `ready` 后成为默认策略。
- hold-out 网点、回投残差、ray angle 和高度不确定度的初始阈值需要用第一批真实固定机位数据校准。
- 未来自动识别采用球网实例/线段检测、关键点检测还是分割模型，需待人工标注样本积累后单独立项。
