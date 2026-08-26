## Why

当前系统已经能够通过球场四角 Homography 和双摄三角测量生成近似 3D 球路，但每台摄像机仍主要依赖假设的内参与平面约束，导致 Z 轴高度、球网附近球路和 3D 场景几何缺少稳定的度量基准。球网同时包含地面以上的已知几何点：按项目约定，两侧边线位置为 91.44 cm、中心为 86.36 cm，因此可以将球网作为非共面标定物，补足从二维球场到度量级 3D 场景的约束。

本变更先支持在同一采集任务内对固定机位进行人工球网标注与手动微调，并让同一场比赛的多个录制视频共享场景标定结果；同时为后续球网自动识别和公开数据集训练预留来源与接口，不在首版内完成模型训练。

## What Changes

- 新增以 `capture_take_id`/采集任务为边界的度量级球场场景标定资产，统一保存球场平面、球网三维高度曲线、各视角相机模型、质量诊断和 revision。
- 在现有球场标定工作流中增加球网人工标注：球网两端、中心及可选的四分之一点、网柱落地点；支持重新进入时恢复草稿和手动微调。
- 将球网顶部定义为非水平的三维 profile，支持两端 91.44 cm、中心 86.36 cm 的标准模型，并允许记录现场实测模型。
- 扩展近似虚拟相机求解，使球场地面点与球网非共面点共同参与相机姿态/内参 refinement；场景标定不可用时保留现有近似 3D/2.5D 降级路径。
- 让双摄球路与球员空间分析引用采集任务级场景标定 revision，并记录标定来源、回投误差、射线几何质量和高度不确定度。
- 让前端 3D 球场从场景模型渲染可变高度球网、网柱和统一 Canonical Court Frame，继续区分 metric 3D、approximate 3D 与 visualization-only 高度。
- 为未来自动球网识别预留 `manual`、`auto_suggested`、`manual_verified` 等 provenance；首版自动识别仅作为后续扩展点，不包含公开数据集搜集、模型训练或自动标注上线。
- 同一采集任务内默认摄像机位置、角度和镜头设置固定，不做逐帧动态重标定；若输入视频或采集配置不再属于同一固定机位，应生成新的场景标定 revision。

## Capabilities

### New Capabilities

- `metric-court-scene-calibration`: 定义采集任务级球场/球网三维场景模型、人工标注、质量门、revision、provenance 以及自动建议扩展点。

### Modified Capabilities

- `court-constrained-virtual-camera`: 相机求解可消费球网非共面控制点进行 metric refinement，并保留现有 approximate fallback。
- `multiview-analysis-input-contract`: 双摄分析输入需要声明并引用采集任务级场景标定 revision 与适用视角。
- `multiview-ball-stereo-evidence`: stereo measurement 记录场景标定来源、几何质量和高度不确定度，不把近似相机结果伪装成 metric 结果。
- `dual-view-3d-segment-reconstruction`: 依据场景标定质量区分 metric height、approximate height 和 visualization-only height，并沿用分层降级。
- `ball-trajectory-visualization`: 3D 球场渲染使用场景模型的球网高度 profile，并向用户表达场景标定和高度可信度。

## Impact

- 后端：球场标定服务、双摄 preflight、`virtual_camera`、stereo evidence、3D segment reconstruction、artifact/composer 和 CaptureTake 资产存储。
- 前端：球场/球网标注工作台、双摄分析向导状态、3D 球场场景和标定质量提示。
- API/artifact：新增采集任务级 scene calibration artifact、revision 引用、net profile、camera model、quality/uncertainty 字段；历史 artifact 继续只读兼容。
- 数据模型：需要区分场景标定的适用采集任务、视角、视频分辨率/镜头配置和发布状态。
- 测试：增加人工标注草稿恢复、标准网高 profile、非共面相机 refinement、固定机位跨视频复用、缺失/低质量标定降级和 3D 场景渲染回归测试。
