## 1. 场景标定数据契约与存储

- [x] 1.1 定义 `metric_court_scene.v1` 的后端/前端类型、revision 状态、scene calibration provenance、camera model source 和 metric validity 枚举。
- [x] 1.2 定义 Canonical Court Frame 下的球网标准 profile、现场 measured profile、控制点结构和单位转换，明确标准两端 91.44 cm、中心 86.36 cm。
- [x] 1.3 在 CaptureTake 目录和 `StorageService` 中增加 scene calibration draft、published revision、history 与读取路径，保证已引用 revision 不可变。
- [x] 1.4 增加场景标定创建、保存草稿、质量检查、发布、查询和 revision 列表 API；所有接口返回结构化状态和 rejection reason。
- [x] 1.5 为 `manual`、`auto_suggested`、`manual_verified` 建立可扩展 annotation provider contract，首版不依赖自动识别模型。
- [x] 1.6 为新 artifact、revision 复用、旧 CaptureTake 缺失场景资产和历史 artifact 只读兼容增加 schema/contract tests。

## 2. 球网人工标注与标定工作台

- [x] 2.1 在现有球场角点标定流程旁增加按 view 的球网标注步骤，支持球网左端、中心、右端必需点和四分之一点/网柱落地点可选点。
- [x] 2.2 复用现有视频抽帧、画面预览和坐标换算能力，在 image-space 与 Canonical 3D control point 之间保持明确映射。
- [x] 2.3 增加 standard/measured profile 选择、现场高度编辑、网柱位置编辑和 profile 回投预览。
- [x] 2.4 支持 draft 保存、离开后恢复、跨视角切换和拖拽微调；每个 view 的完成状态 SHALL 可单独诊断。
- [x] 2.5 增加人工确认发布前的完整性提示，区分“点位未完成”“profile 未确认”“质量门未通过”和“可发布”。
- [x] 2.6 为工作台补充组件测试，覆盖最小三点、可选点缺失、draft 恢复、标准/实测 profile 切换和错误状态。

## 3. 球网辅助相机模型与质量门

- [x] 3.1 实现标准/实测球网 profile 到 canonical 3D 控制点和采样曲线的确定性生成，处理实际网柱超出边线的独立坐标。
- [x] 3.2 以现有 Homography virtual camera 作为初值，将 court ground points 与 net non-planar points 接入 robust reprojection refinement。
- [x] 3.3 保留现有中心主点、`fx = fy`、零径向畸变、前方性、姿态消歧和 Canonical Court Frame 检查，并输出 net/court 分项 residual。
- [x] 3.4 增加 hold-out 控制点、双视角 ray geometry、深度范围、视角覆盖和 provenance 完整性质量门，生成 `ready`/`degraded`/`invalidated` 结果。
- [x] 3.5 从相机残差与双摄几何估计 `height_uncertainty_ft` 或等价高度不确定度摘要，并记录不确定度来源。
- [x] 3.6 为无场景标定、控制点不足、姿态消歧失败、视差不足和 hold-out 失败增加显式 fallback/rejection diagnostics。
- [x] 3.7 增加合成相机/已知网高数据测试，验证标准网 profile 回投、相机 refinement、Canonical frame 对齐和失败降级。

## 4. 双摄输入与采集任务复用

- [x] 4.1 在双摄分析创建请求、Parent metadata、`jointViewInputs` 和 runtime input bundle 中加入 `scene_calibration_revision`、适用 view ids、状态和 fallback mode。
- [x] 4.2 扩展 MultiView preflight，验证 scene revision 属于当前 `capture_take_id`、覆盖所有目标 view 且 camera/video/image-size provenance 匹配。
- [x] 4.3 在 metric 模式下拒绝缺少 ready revision 的任务；在显式 approximate 模式下保留现有 virtual camera 路径并写入降级原因。
- [x] 4.4 将 scene reference 纳入 job input/config signature，确保同一采集任务切换 revision 或 fallback mode 时生成可区分、可复现的分析任务。
- [x] 4.5 验证同一固定机位采集任务的多个录制视频可以复用同一 revision，且不执行逐帧或逐视频动态重标定。
- [x] 4.6 增加跨采集任务、camera identity、图像尺寸和配置不匹配时的 preflight contract tests。

## 5. Stereo evidence 与 3D 重建接入

- [x] 5.1 扩展 `BallStereoMeasurement`、stereo evidence artifact 和重建 sample，保存 scene revision、camera model source、metric validity、height uncertainty 和质量分量。
- [x] 5.2 让正式 joint 球链路优先消费 ready scene revision 生成的 refined projections，同时保留旧 artifact 和 approximate virtual camera fallback。
- [x] 5.3 将 scene residual、hold-out 质量和 ray geometry 接入 stereo quality/high-quality anchor 门控，低质量证据保留审计但不得成为 metric anchor。
- [x] 5.4 更新 segment reconstruction 的高度资格和指标资格，区分 `metric_multiview`、`approximate_multiview`、`visualization_only` 与 `unavailable`。
- [x] 5.5 传播场景标定 mismatch、revision invalidation、低 ray angle、动态同步误差和负高度等独立诊断，不互相覆盖。
- [x] 5.6 更新 composer、artifact adapter 和 API 读取逻辑，保证旧 v1/v2/v3 轨迹仍可读取且不会被回写为新 scene semantics。
- [x] 5.7 为 metric/approximate/2.5D 混合段、场景缺失、场景失效和高度不确定度传播增加后端回归测试。

## 6. 3D 球场场景与前端表达

- [x] 6.1 扩展前端报告类型和 view model，读取 scene calibration profile、net model、scene status、metric validity 与 height uncertainty。
- [x] 6.2 将现有固定高度 BoxGeometry 球网替换为由 profile 采样生成的球网主体、顶部带和网柱几何，并保持现有五个固定视角和交互控制。
- [x] 6.3 保证球网、球场线、球路和球员位置使用同一 Canonical Court Frame 与单位语义。
- [x] 6.4 在场景或技术详情中区分现场/标准 metric scene、approximate fallback 和 visualization-only 高度；缺少 profile 时不得伪装成现场实测网几何。
- [x] 6.5 保持轨迹来源线型、断点、display eligibility 和现有 WebGL 错误状态不回归。
- [x] 6.6 增加 Three.js 场景测试，覆盖标准网高两端/中心、实测 profile、缺失 profile、场景 revision 状态和高度来源表达。

## 7. 真实数据验收与文档

- [x] 7.1 准备一个同一 `capture_take_id` 下的固定双摄样例，分别保存两路人工球网标注、标准/实测 profile、scene revision 和 hold-out 点。
- [x] 7.2 对旧 Homography virtual camera 与 net-assisted camera 做静态 A/B，记录 court/net reprojection、ray geometry、深度范围和高度不确定度。
- [x] 7.3 对同一比赛的多个录制视频验证 scene revision 复用、无逐视频重复标注、输入 provenance 一致和任务重跑可复现。
- [x] 7.4 对动态球路验证球网附近高度、穿网事件、3D segment 状态、speed/peak-height eligibility 和 approximate fallback 语义。
- [x] 7.5 更新场景标定、双摄输入、artifact 字段和前端降级说明文档，明确首版不包含公开数据集训练和自动标注上线。
- [x] 7.6 提供 feature flag 或显式 fallback mode 的回滚验证，不删除历史分析、stereo evidence 或 scene calibration revision。
