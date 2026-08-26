## 1. 基线与契约准备

- [x] 1.1 为固定回放任务建立 P2/P4 8–13 秒和 33.166 秒球路边界的测试 fixture，记录 reference view、processed tick、segment_id、primary_view_id 与现有输出。
- [x] 1.2 明确并实现可选的 `render_view_id`、target-view path availability、boundary policy 和 projection rejection diagnostics 字段，保持旧 artifact 读取兼容。
- [x] 1.3 增加 schema/API contract test，验证新增字段缺失时走兼容 fallback，且禁止把另一摄像头 image-space 坐标静默当作当前视频坐标。

## 2. 参考视角球员关联稳定

- [x] 2.1 审核 `GlobalPlayerAssociator` 的 incumbent、challenger 和 `PendingReassociation` 状态边界，确保 `no_association_input`、`ambiguous` 和低于 `switch_margin` 的候选不触发单帧切换。
- [x] 2.2 将连续强 challenger 的几何可行性、代价 margin、identity 一致性和真实时间窗口接入 reassociation 判定，并保留可配置的确认帧数。
- [x] 2.3 为短时漏检、P2/P4 接近交叉、歧义 pair、连续强证据重关联分别补充 association 单元测试和 diagnostics 断言。
- [x] 2.4 在 reference-view association diagnostics 中记录 incumbent 保持、pending、reassociation 成功及拒绝原因，保证可按 player/view/tick 查询。

## 3. Fused overlay 投影与展示几何稳定

- [x] 3.1 在 fused overlay builder 中统一使用任务 `reference_view_id` 生成 target-view projection，禁止将 donor view 的 image-space bbox直接作为目标视角 bbox。
- [x] 3.2 为 projected bbox 增加目标视角连续性、脚点速度、bbox 尺寸变化、图像边界和与其他 strong/accepted bbox 的碰撞门控。
- [x] 3.3 确保投影拒绝时只能降级为稳定 presentation geometry、`PROJECTED_POINT` 或 `HIDDEN`，且 synthetic bbox 不刷新 `TargetViewBBoxMemory` 与 `ViewPersonScaleProfile`。
- [x] 3.4 扩展 overlay diagnostics，记录 projection gate、collision、continuity rejection、geometry hold 和降级原因，并保持 `evidence_type` 与 `display_state` 正交。
- [x] 3.5 在展示状态机中按 `(job_id, reference_view_id, canonical_player_id)` 维护 presentation geometry，加入真实时间差驱动的位移/尺寸连续性门控。
- [x] 3.6 验证 `base_observed → cross_view_projected → base_observed` 快速交替时不会产生 bbox 全尺寸跳变，同时验证新的 strong real bbox 仍可立即恢复。
- [x] 3.7 增加新 job、roster reset、reference view 变化时清空 hold timer、continuity counter 和 presentation geometry 的测试。

## 4. 球路 artifact 的目标视角与边界语义

- [x] 4.1 在 reconstructed trajectory adapter/产物中写入任务级 `render_view_id`，默认使用 `reference_view_id`，并保留 segment `primary_view_id` 作为重建质量字段。
- [x] 4.2 为每个 segment 提供目标渲染视角的 image path 或明确的 target-view reprojected path；目标视角路径缺失时输出 video-overlay unavailable/diagnostic-only 原因。
- [x] 4.3 将视频 display window 规范化为半开区间 `[start_ms, end_ms)`，定义共享边界、公共端点和 retention tail 的序列化语义。
- [x] 4.4 为 33.166 秒 `flight-42`/`flight-43` 边界、primary view 从 cam_2 切到 cam_1、目标视角 path 缺失分别增加 artifact/adapter 测试。

## 5. 前端球路 compositor

- [x] 5.1 在 `VisionPage`/`VideoAnalysisCard` 传递任务 `render_view_id`，移除未显式指定时按每个 segment `primary_view_id` 绘制视频 path 的行为。
- [x] 5.2 更新 hybrid ball path resolver，只消费 `image_paths_by_view[render_view_id]` 或等价 target-view path；无目标视角坐标时跳过视频 path并保留 skip reason。
- [x] 5.3 实现半开时间窗口和唯一 active segment 选择：后继 segment 开始后停止前一段 retention，最多保留一个去重公共端点。
- [x] 5.4 对 segment_id、render_view_id、时间窗口和 boundary policy 做确定性去重，确保拖动、暂停、往返播放在边界前后得到相同 active segment 集合。
- [x] 5.5 为 33 秒双轨迹回归场景、不同 primary view 的坐标隔离、重复 segment 输入和缺少 target-view path 增加前端单元测试。

## 6. 集成验收与发布

- [x] 6.1 运行后端 association、overlay、trajectory artifact 与前端 compositor 的定向测试，确认旧 artifact 兼容路径不回归。
- [x] 6.2 使用固定任务回放 8–13 秒，验证 P2/P4 不发生单帧身份互换、投影框不覆盖可信真实框、bbox 几何连续且 evidence provenance 诚实。
- [x] 6.3 使用固定任务回放 32–35 秒，验证 33.166 秒边界不同时绘制两个片段，且所有视频球路坐标属于同一 `render_view_id`。
- [x] 6.4 对全屏与非全屏播放器、不同 frameStride 和旧/新 artifact 分别执行视觉验收并记录 diagnostics 对比。
- [x] 6.5 更新相关 API/artifact 文档与变更日志，确认 feature flag 或兼容开关可在异常时回滚而不删除历史产物。
