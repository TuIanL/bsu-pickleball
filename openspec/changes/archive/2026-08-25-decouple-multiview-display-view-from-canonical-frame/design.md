## Context

当前 `joint_tracking_v2` 使用 `referenceViewId` 作为共同时间轴、Parent 主视频和部分视觉产物的参考。`canonicalFrameId` 与每路 `courtOrientation` 属于 CaptureTake 的稳定分析输入，不能在结果展示时改变。当前正式 fused Player overlay 主要输出 reference view；球路 artifact 已经能够保存按 view 的 image-space path，但 `VideoAnalysisCard` 仍然只接收一个视频源和一组 overlay frame。

用户需要在分析完成后查看同一任务的 A/B 两个视频视角。切换后，视频画面应使用目标机位的像素坐标；Player 身份、球路归属、canonical 小地图位置和时间语义仍必须与同一次 joint 分析保持一致。该切换不应创建新任务、重新运行 detector/tracker，也不能修改已经持久化的 Canonical Court Frame。

整体关系如下：

```text
                    ┌────────────────────────────┐
                    │ joint analysis (once)       │
                    │ referenceViewId = default   │
                    │ canonicalFrameId = immutable │
                    └─────────────┬──────────────┘
                                  │
                 ┌────────────────┴────────────────┐
                 │                                 │
        canonical player/ball state       view-scoped projections
        P1..P4 + court coordinates         cam_1 / cam_2 image paths
                 │                                 │
                 └──────────────┬──────────────────┘
                                ▼
                 displayViewId = cam_1 | cam_2
                 video + Player + ball overlay
                 minimap remains canonical
```

## Goals / Non-Goals

**Goals:**

- 为已完成的双摄任务提供 A/B 展示视角切换，默认使用任务的 `referenceViewId`。
- 在切换后保持 canonical timestamp、视频媒体时间、Player overlay、球路 image-space path 和小地图状态一致。
- 保证 P1-P4 的身份、击球归属和队伍/场地区域不因视角切换而变化。
- 让 A/B 两路视角的 overlay 从同一份 joint evidence、roster 和 canonical tick 生成，不重复运行视觉模型。
- 对旧 artifact、缺失目标视角投影、遮挡和不完整媒体映射提供安全降级。
- 让设置页重试时沿用已存在的 canonical frame，不再把展示选择误当作端点重定义。

**Non-Goals:**

- 不改变 joint 的 reference timeline、同步算法、球员身份算法或 Canonical Court Frame 定义。
- 不支持用户在结果页重新标定球场朝向；真实朝向修正应通过新的场景/标定 revision 处理。
- 不在任务运行中切换分析引擎的 reference view；本变更只处理分析完成后的展示切换。
- 不为历史仅含单路 overlay 的 artifact 猜测或伪造另一视角的 bbox。
- 不引入第三方播放器、实时流媒体或新的识别模型。

## Decisions

### 1. 将 `displayViewId` 与任务输入分离

Parent 继续持久化 `referenceViewId`、`canonicalFrameId`、`jointViewInputs` 和 `courtOrientation`，这些字段属于一次分析的不可变输入。前端新增 `displayViewId`，默认值为 `referenceViewId`，只表示当前展示选择，不进入 AnalysisJob 创建请求，也不参与 input/config signature。

这样可以保证用户切换视角不会触发新的 preflight、canonical frame conflict 或重复识别。用户如果确实修改物理朝向，必须走显式标定 revision 流程，而不是通过展示按钮完成。

备选方案是切换时重新创建一个以 B 为 reference 的新任务。该方案会增加计算成本、产生两份可能不一致的 roster/trajectory，并让“查看另一个机位”变成“再次分析”，因此不采用。

### 2. 使用统一 canonical 时间驱动两个视频

播放控制器内部维护 `canonicalTimeMs`，目标 view 的视频时间由持久化 sync mapping/真实 source PTS 映射得到。切换视角时先保存当前 canonical time，再将其映射到目标视频；不得直接复用 reference view 的 raw frame index 或把两个视频的 `currentTime` 当作同一物理时刻。

展示 manifest 或等价的 read-only API SHALL 返回每个 view 的 `video_id`、camera identity、媒体尺寸以及可用于 canonical time → source timestamp/frame 的映射引用。映射不可用时，目标视角切换应进入明确不可用状态，并保留当前可靠的 canonical 数据。

### 3. Player overlay 使用 view-scoped frames，共享 canonical identity

将正式 Player overlay 扩展为 v2 结构，在同一个任务 artifact 中按 `view_id` 保存 frames，或由 API 以 view 参数返回同一份 view-scoped frames。每个 view 的 frame 仍以 canonical tick/timestamp 对齐，每个 entity 使用同一套 `Player_1`..`Player_4` canonical identity。

overlay builder 消费同一份 global roster 和 joint evidence，对不同 view 只执行投影/坐标选择，不重新做 track-to-player matching。某个 view 没有真实 bbox 时，可以保留 canonical footpoint、投影状态和 uncertainty；若不足以生成可靠 bbox，则 `bbox` 必须为 `null`，不得把另一球员的框借给当前球员。

备选方案是前端根据小地图 canonical 坐标反投影生成 bbox。该方案会绕过既有 view geometry、scale profile 和 overlay evidence 门控，容易把 court 坐标误当像素坐标，因此不采用。

### 4. 小地图保持 canonical，视频 overlay 随 view 切换

小地图的 Player 位置、球路和标签继续使用 canonical court 坐标；切换 A/B 不改变 P1-P4 的位置或颜色。如果目标 view 的 image-space path 不可用，视频层只显示相应的缺失/不可用状态，小地图仍可继续显示可靠的 canonical 轨迹。

球路优先消费 `image_paths_by_view[displayViewId]`；不存在目标 view path 时，不从 `court_xy` 伪造像素曲线，改为关闭该视频球路层并保留明确状态。

### 5. 展示选择通过 URL 保持，但不与 workspace `view` 混用

使用独立查询参数 `displayView=cam_1|cam_2` 保存展示机位，避免与已有的 workspace `view=analysis|trajectory|technical` 语义冲突。非法或不可用的值回退到 `referenceViewId`，并使用 replace 语义更新当前分析工作区 URL；Tab 切换和刷新继续保留 `analysisJob` 与 `displayView`。

### 6. Canonical frame 只读复用与兼容修复

设置页在已有 canonical frame 的 take 上应读取其物理端点和 `orientation_by_view`，恢复当前配置并禁止展示选择修改它。创建请求的 `canonicalFrame` 必须使用已解析的物理定义；scene calibration 的 `canonical_frame_id` 也应引用实际的 `ccf_...` frame id，而不是重新拼接一个 take 字符串。

历史任务没有 canonical frame 或展示 manifest 时，继续默认 reference view；历史 v1 overlay 只包装为 reference view 可用，不声明 cam_2 overlay 可用。

### 7. 生成两路展示产物但不重复检测

joint compose 阶段使用已存在的 F0/F1 evidence、global roster、canonical positions 和每路 view geometry，一次性生成两路 view-scoped Player overlay；球路复用已有的每视角 image path。该方式增加存储和投影输出成本，但切换时无需等待后台重算，也能保证 A/B 两路共享同一个 tick 和身份结果。

## Risks / Trade-offs

- **[两路 overlay 使 artifact 体积增加]** → 只保存必要的 bbox/footpoint/状态字段，保留 lazy API 读取；不重复保存 detector raw 数据。
- **[两个视频的媒体时钟/PTS 不完全一致]** → 所有切换和 overlay 解析使用 canonical timestamp 与 source PTS mapping，并在不可映射时显式显示 unavailable。
- **[B 机位几何质量不足]** → 允许 Player footpoint 或球路层按质量降级，但禁止跨球员借框、像素坐标伪投影或身份重排。
- **[历史 artifact 只有 reference view]** → 读取层归一化为单 view bundle，切换按钮禁用或提示“该历史任务没有 B 机位展示产物”。
- **[展示状态与分析输入再次耦合]** → API schema、input signature 和前端创建请求明确排除 `displayViewId`，增加“切换不创建任务”回归测试。
- **[现有 canonical conflict 仍被重试触发]** → 设置页优先读取已保存 frame；preflight 错误增加既有 frame 定义与请求定义的结构化对比。

## Migration Plan

1. 增加 display view 类型、展示 manifest 和前端 URL 状态；默认从 `referenceViewId` 推导，不改变旧任务。
2. 扩展 joint overlay 产物为 view-scoped v2，并为旧 v1 artifact 增加只读归一化适配器。
3. 接入统一 canonical time controller，完成视频、Player overlay、球路和小地图的 view 切换。
4. 修复设置页 canonical frame 恢复和 canonical frame id 引用，增加同一 take 重试/切换回归用例。
5. 在真实双摄任务上验证 A→B→A、拖动时间轴后切换、遮挡、缺帧和四名 Player 身份稳定性。
6. 若新 view-scoped artifact 生成失败，保留旧 reference-view 结果并将切换按钮降级为不可用；不删除历史 artifact。可通过 feature flag 关闭 v2 view bundle 生成。

## Open Questions

- view-scoped Player overlay v2 是一次性写入完整 `views` map，还是由统一 artifact API 按 `view_id` 懒加载；默认方案偏向完整写入、按 view 读取。
- B 机位的 Player bbox 应优先使用该视角真实观测，还是优先使用由 canonical 位置投影的 cross-view evidence；需要结合现有 `fused_overlay_builder` 的质量门确定优先级。
- 展示按钮是否同时放在视频 header 和双摄协同详情页；默认建议只在主视频分析卡放一个全局选择器，避免多个控件产生状态竞争。
