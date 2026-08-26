# multiview-display-view-switching Delta

## ADDED Requirements

### Requirement: 默认展示机位与当前展示机位分离

系统 SHALL 为每个已完成的双摄 Parent 暴露 `referenceViewId` 与可用 `displayViewIds`。默认 `displayViewId` SHALL 等于 `referenceViewId`；用户 SHALL 能在可用 view 中选择当前展示机位，且该选择 SHALL 不改变 `referenceViewId`、`canonicalFrameId`、`courtOrientation` 或分析结果。

#### Scenario: 默认打开双摄结果

- **WHEN** 用户首次打开一个包含 `cam_1` 与 `cam_2` 的已完成 joint 任务
- **THEN** 页面 SHALL 默认展示该任务的 `referenceViewId`
- **AND** SHALL 显示可用的 A/B 展示机位切换控件

#### Scenario: 用户切换展示机位

- **WHEN** 用户从 `cam_1` 切换到 `cam_2`
- **THEN** 页面 SHALL 只改变 `displayViewId` 与展示层数据源
- **AND** SHALL NOT 创建新 AnalysisJob、重新运行识别或修改任务级 canonical 输入

### Requirement: 展示视角使用统一 canonical 时间

系统 SHALL 以 `canonical_timestamp` 作为双摄展示的时间权威。切换到目标 view 时，播放器 SHALL 通过该 view 的 source timing/sync mapping 定位到对应真实媒体时间或帧；系统 SHALL NOT 直接把 reference view 的 raw frame index 当作目标 view 的媒体时间。

#### Scenario: 播放中切换视角

- **WHEN** reference view 播放到 canonical 时间 `t` 且用户切换到另一 view
- **THEN** 目标视频 SHALL 定位到与 `t` 对应的 source timestamp/frame
- **AND** Player overlay、球路和小地图 SHALL 继续解析同一个 canonical tick

#### Scenario: 目标 view 无法映射时间

- **WHEN** 目标 view 缺少有效 timing mapping 或目标时刻超出其有效区间
- **THEN** 视频层 SHALL 显示结构化不可用状态
- **AND** SHALL NOT 伪造目标帧或把另一 view 的像素坐标绘制到当前视频

### Requirement: Player 身份在视角切换中保持稳定

系统 SHALL 使用 joint 分析生成的 canonical Player roster 作为所有 view 的唯一身份来源。相同 canonical tick 下，A/B view 中表示同一球员的 entity SHALL 保持相同的 `player_id`、`render_slot`、标签、颜色、击球归属和队伍语义；展示视角切换 SHALL NOT 根据局部 track、检测顺序或画面位置重新编号。

#### Scenario: P1 从 A 机位切换到 B 机位

- **WHEN** A 机位当前显示 P1，用户切换到 B 机位
- **THEN** B 机位对应的 entity SHALL 仍显示为 P1
- **AND** 只允许改变该 entity 的 image-space bbox、footpoint、evidence 和 view-specific quality

#### Scenario: 某球员在目标机位不可见

- **WHEN** 某 Player 在目标 view 当前 tick 没有可靠图像证据
- **THEN** 该 Player SHALL 保留 canonical identity
- **AND** bbox SHALL 为 `null` 或显示明确的不可见/遮挡状态
- **AND** 系统 SHALL NOT 把其他 Player 的 bbox 分配给该 Player

### Requirement: Player、球路与小地图使用正确坐标空间

视频上的 Player 与球路 SHALL 只消费当前 `displayViewId` 的 image-space 坐标。小地图 SHALL 继续消费统一 Canonical Court Frame 的 court 坐标和同一 canonical tick；系统 SHALL NOT 将一个 view 的像素坐标绘制到另一个 view 的视频上。

#### Scenario: 切换后显示 Player 和球路

- **WHEN** 当前 `displayViewId=cam_2`
- **THEN** 视频 Player overlay SHALL 来自 `cam_2` 的 view-scoped frames
- **AND** 球路 SHALL 来自 `image_paths_by_view.cam_2` 或等价的目标 view path
- **AND** 小地图 SHALL 使用同一 tick 的 canonical Player/ball 位置

#### Scenario: 目标 view 缺少球路路径

- **WHEN** 目标 view 没有该时间段的合法 image-space ball path
- **THEN** 视频球路层 SHALL 显示不可用或隐藏
- **AND** 小地图中的 canonical 球路 SHALL 仍可在其自身质量门通过时展示
- **AND** 系统 SHALL NOT 从 `court_xy` 直接伪造视频像素曲线

### Requirement: 展示机位状态可刷新恢复

系统 SHALL 使用独立于 workspace `view` 的 URL 参数保存 `displayViewId`。刷新、分析工作区内部 Tab 切换和从结果页返回时 SHALL 保留合法展示机位；缺失、非法或已不可用的值 SHALL 安全回退到 `referenceViewId`。

#### Scenario: 刷新后保持 B 机位

- **WHEN** 用户在 `displayView=cam_2` 的分析工作区刷新页面
- **THEN** 页面 SHALL 继续选择 `cam_2`
- **AND** SHALL 保留原有 `analysisJob` 与 workspace `view` 参数

#### Scenario: 非法展示机位

- **WHEN** URL 中的 `displayView` 不是任务可用 view
- **THEN** 页面 SHALL 回退到 `referenceViewId`
- **AND** SHALL NOT 请求或渲染未知 view 的 overlay
