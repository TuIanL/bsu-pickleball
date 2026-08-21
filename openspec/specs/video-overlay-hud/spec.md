# video-overlay-hud Specification

## Purpose
TBD - created by archiving change redesign-video-analysis-overlay. Update Purpose after archive.
## Requirements
### Requirement: 比例正确且视频友好的球场 HUD

系统 SHALL 在真实视频分析播放区域内提供半透明、可读且不遮挡主要视频内容的球场 HUD。HUD SHALL 使用标准匹克球场几何保持 20×44 英尺的纵横比，正式球场 SHALL 比 tracking bounds 更突出；HUD 尺寸 SHALL 在桌面、窄屏和全屏模式下保持稳定的宽高约束。HUD SHALL 默认收起，仅在用户主动展开时显示，且展开后 SHALL 不遮挡底部播放控件。

#### Scenario: 桌面视频显示 HUD

- **WHEN** 用户打开包含球员投影轨迹的真实分析视频
- **THEN** 视频右上侧显示球场 HUD 展开按钮，正式球场线、球网、厨房区和边界图例清晰可辨，且 HUD 不覆盖底部播放控件

#### Scenario: 窄屏视频显示 HUD

- **WHEN** 用户在窄屏设备上打开真实分析视频
- **THEN** HUD 缩放或调整位置以保持球场比例，并且不与视频时间、播放按钮或图层控制发生重叠

#### Scenario: HUD 默认收起

- **WHEN** 用户打开真实分析视频且尚未主动展开球场 HUD
- **THEN** 只显示地图展开按钮，不显示完整球场 HUD，避免遮挡视频与播放控件

#### Scenario: 用户展开 HUD 后再次收起

- **WHEN** 用户点击地图展开按钮显示 HUD，再次点击同一按钮
- **THEN** HUD 收起，只保留展开按钮，且视频播放状态与图层状态保持不变

#### Scenario: HUD 不显示 tracking bounds

- **WHEN** 当前设置关闭边界诊断或没有有效越界点
- **THEN** HUD 仍显示正式球场，不因隐藏 tracking bounds 而改变正式球场的比例或位置

### Requirement: 同步显示球员移动轨迹

系统 SHALL 按视频当前播放时间显示稳定球员身份的当前位置和时间尾迹。每名球员 SHALL 使用稳定的视觉颜色和 `P1` 至 `P4` 标签；尾迹 SHALL 表达时间方向，当前位置 SHALL 具有明显的焦点标记，且相邻轨迹点存在足够时间缺口或位移超过断线阈值时 MUST 断线。

#### Scenario: 四名球员轨迹可用

- **WHEN** 当前时间窗口包含四名稳定球员的有效 `court_point`
- **THEN** HUD 显示四条相互可区分的球员尾迹、当前位置和身份标签，不显示原始 detector `track_id`

#### Scenario: 球员轨迹存在缺口

- **WHEN** 同一球员相邻有效点之间的 timestamp 差超过轨迹连接阈值
- **THEN** HUD 将轨迹拆成多个片段，不绘制跨越缺口的直线，并保留最近有效位置的状态

#### Scenario: 球员轨迹存在大位移跳变

- **WHEN** 同一球员相邻有效点的球场位移超过断线阈值（默认 6 英尺，可配置）
- **THEN** HUD 将轨迹拆成多个片段，不绘制跨越跳变的直线，避免出现连接两个不相关位置的虚假连线

#### Scenario: 当前窗口没有球员点

- **WHEN** 当前播放时间附近没有任何有效球员投影点
- **THEN** HUD 隐藏过期当前位置，显示“当前时间无有效球员投影”或等价降级状态，不显示静态模拟球员

### Requirement: 显示可解释的球员速度摘要

系统 SHALL 在存在足够连续球员坐标和可确认坐标单位时计算并显示当前位置的速度摘要，不得显示球员移动方向指示。速度单位 SHALL 与输入 coordinate metadata 一致；无法确认单位或点数不足时，系统 SHALL 明确显示速度不可用。

#### Scenario: 球员速度可计算

- **WHEN** 某球员在短时间窗口内存在至少两个连续有效球场坐标，且坐标单位可确认
- **THEN** HUD 在摘要区域显示带单位的速度值，且不在球员当前位置渲染方向箭头

#### Scenario: 速度单位不可确认

- **WHEN** 球员轨迹存在但 artifact 没有可确认的坐标单位
- **THEN** HUD 不把英尺或像素误标为米每秒，并显示“速度不可用”或等价状态

### Requirement: 显示球的图像轨迹、平面投影和弹跳候选

系统 SHALL 将球轨迹按空间语义分层显示：视频主画面使用 `image_xy` 表达图像中的球路，小地图使用 `court_xy` 表达球场平面投影；弹跳候选 SHALL 使用独立 marker。系统 SHALL 区分检测点、插值点和低置信度候选的视觉强度或线型。

#### Scenario: 球轨迹可用

- **WHEN** 当前真实任务包含带有效 `image_xy` 的球轨迹样本
- **THEN** 视频中显示高对比度渐隐球路和当前球点，小地图中显示可同步的球场平面投影，并在状态摘要中显示球层可用

#### Scenario: 球轨迹存在长缺口

- **WHEN** 相邻球样本之间存在超过连接阈值的时间缺口
- **THEN** 视频和小地图均断开轨迹段，不用直线伪造缺失期间的球路

#### Scenario: 球样本为插值点

- **WHEN** 球轨迹样本标记为 `interpolated`
- **THEN** 该段以较低透明度、虚线或等价方式显示，并且不被标记为直接检测结果

#### Scenario: 弹跳候选接近当前时间

- **WHEN** 弹跳候选的 timestamp 在当前播放时间窗口内
- **THEN** 视频和小地图显示独立的弹跳 marker，并提供候选置信度或候选状态，而不把候选描述为已确认击球或得分事件

#### Scenario: 用户查看空中球路

- **WHEN** 用户打开球路显示且当前 artifact 只有二维图像坐标或球场平面坐标
- **THEN** 系统显示“视觉估算球路”或等价说明，不宣称真实飞行高度、三维球速或过网高度已被测量

### Requirement: 独立控制视频分析图层

系统 SHALL 为人框、骨架、球点、球路和弹跳候选提供独立的显示/隐藏控制。控制 SHALL 暴露当前状态、在对应 artifact 不可用时禁用或说明原因，且切换图层不得改变视频播放位置或其他图层的数据状态。

#### Scenario: 用户隐藏球员骨架

- **WHEN** 用户关闭骨架图层
- **THEN** 视频隐藏骨架关节和连线，但保持人框、球员 HUD、球轨迹、播放和小地图状态不变

#### Scenario: 用户只查看球路

- **WHEN** 用户关闭人框、骨架和弹跳候选并保留球点与球路
- **THEN** 视频只显示球相关图层，小地图仍按照球路开关显示球的平面投影

#### Scenario: 球 artifact 不可用

- **WHEN** 当前任务没有球轨迹、球轨迹加载失败或状态为 unavailable/no-candidates
- **THEN** 球点、球路控制显示不可用原因，系统不显示 demo 球或静态模拟球路

### Requirement: HUD 状态和真实数据来源清晰

系统 SHALL 在 HUD 或其相邻状态区域显示当前视频时间、可见球员数量、球层状态和必要的候选/置信度摘要。所有可见轨迹和 marker SHALL 来自当前真实 job artifact；loading、failed、unavailable、no-candidates 和当前时间无点 SHALL 使用不同或可理解的状态文案。

#### Scenario: 真实任务图层正在加载

- **WHEN** 视频已可播放但球员、球或弹跳 artifact 仍在加载
- **THEN** 视频播放和已可用图层保持交互，HUD 只对对应图层显示 loading 状态

#### Scenario: 真实任务图层加载失败

- **WHEN** 某一 artifact 请求失败
- **THEN** HUD 标记该图层 failed 并保留其他成功加载的图层，不将整个视频区域替换成全页错误状态

#### Scenario: 当前状态仅有候选数据

- **WHEN** 任务存在弹跳候选或球轨迹但尚未实现完整击球、回合或得分语义
- **THEN** HUD 使用“候选”“估算”或等价措辞，不把候选提升为已确认比赛事件

### Requirement: 高帧率播放期间保持可用性能

系统 SHALL 使用现有视频帧时间同步机制更新 HUD，并 SHALL 只处理当前时间窗口内的轨迹数据。轨迹渲染 SHALL 对单条轨迹和球路设置最大绘制点数或稳定降采样上限，避免完整 artifact 在每个视频帧被重复排序和重建。

#### Scenario: 60 FPS 视频播放

- **WHEN** 用户播放 60 FPS 或等价高帧率真实视频
- **THEN** HUD 跟随视频帧时间更新当前位置和球点，不依赖低频 `timeupdate` 才刷新

#### Scenario: 长视频轨迹点很多

- **WHEN** 任务 artifact 包含数万条球员或球轨迹点
- **THEN** HUD 只筛选当前时间窗口并使用稳定降采样，播放控件和视频画面仍保持可交互

### Requirement: 小地图球场方向与视频拍摄方向一致

小地图 SHALL 按视频拍摄方向渲染球场：近端（摄像头/我方）底线在底部、远端（对方）底线在顶部，球网居中。球员点的球场投影位置 SHALL 与其在视频中的左右/近远方向一致。

#### Scenario: 近端球员显示在小地图底部

- **WHEN** 视频中的球员位于近端底线（画面下方、摄像头侧），且其 `court_point` 的 y 值接近球场远端坐标
- **THEN** 该球员的小地图点显示在底部（近端底线一侧），与视频位置方向一致

#### Scenario: 小地图方向与详情页场地图一致

- **WHEN** 同一名球员同时出现在小地图与轨迹详情页的场地图中
- **THEN** 两处渲染的近/远方向一致，不出现"小地图在顶部、详情页在底部"的矛盾

### Requirement: 滞后球员点位显示停滞状态

小地图 SHALL 对落后于当前视频播放时间超过新鲜度阈值的球员点显示停滞/丢失状态，不得将其标记为"当前位置"。停滞球员 SHALL 降低透明度并去除当前位置光晕，摘要区域 SHALL 显示停滞或丢失标记。

#### Scenario: 球员数据短时间未更新

- **WHEN** 某球员最近有效点的 timestamp 落后当前播放时间超过新鲜度阈值（默认 0.5 秒）
- **THEN** 小地图将该球员标记为停滞，降低透明度、去掉当前位置光晕，并在摘要中显示丢失标记

#### Scenario: 球员数据恢复正常更新

- **WHEN** 停滞球员随后出现新的有效点且其 timestamp 回到当前播放时间附近
- **THEN** 小地图恢复该球员的当前位置显示

### Requirement: 叠加样式按 evidence_type 区分

视频叠加层的展示职责 SHALL 分三层：`player_id` 决定 identity hue（同一 Player 跨 evidence 恒定的主色，MUST NOT 因证据来源如 Cam2 辅助/投影/预测而改变）；`display_state` 决定 geometry topology（BOX / POINT / HIDDEN）；`evidence_type` 决定 provenance style（real / assisted / projected / predicted 的实线 / 虚线 / 透明度 / badge），MUST NOT 改变 identity hue。`evidence_type` 为 `base_observed` / `guided_observed` / `refined_observed` SHALL 用实线真实检测框；`cross_view_projected` SHALL 用虚线或半透明框（携带协同补全语义）；`predicted_only` SHALL 用淡化 footpoint / identity badge / uncertainty halo。synthetic 证据 SHALL NOT 借助颜色伪装为真实检测实线框。

#### Scenario: 真实观测实线

- **WHEN** `evidence_type` 为 `base_observed` / `guided_observed` / `refined_observed`
- **THEN** 叠加层 SHALL 以实线渲染该球员的 bbox
- **AND** SHALL 使用与身份一致的颜色

#### Scenario: 协同补全虚线

- **WHEN** `evidence_type` 为 `cross_view_projected`
- **THEN** 叠加层 SHALL 以虚线或半透明样式渲染
- **AND** SHALL 保持该球员身份颜色不变

#### Scenario: 预测仅光圈

- **WHEN** `evidence_type` 为 `predicted_only`
- **THEN** 叠加层 SHALL 以淡化 footpoint / identity badge / uncertainty halo 渲染
- **AND** SHALL NOT 渲染为实线检测框

#### Scenario: 身份色跨证据恒定

- **WHEN** 同一 `Player_N` 在 `base_observed` / `guided_observed` / `refined_observed` / `cross_view_projected` / `predicted_only` 之间切换
- **THEN** 人物主色 SHALL 保持身份色不变（`identity_color_switch_count` SHALL 为 0）
- **AND** evidence source SHALL 通过线型 / 透明度 / badge 表达

### Requirement: fused overlay 播放时间解析

播放时间解析 SHALL 按 canonical `player_id`（而非本地 `track_id`）对 fused overlay 帧做前后帧插值；SHALL 支持 gap 语义：短 gap 合法插值，超过 `max_overlay_gap` SHALL 禁止跨 gap 插值；`predicted_only` 超过 TTL SHALL 立即隐藏。

#### Scenario: 按 player_id 稳定插值

- **WHEN** 播放时间位于两帧之间且同一 `player_id` 在两帧均存在
- **THEN** 叠加层 SHALL 按时间比例插值该球员 bbox / footpoint

#### Scenario: 跨 gap 禁止插值

- **WHEN** 相邻两帧间隔超过 `max_overlay_gap`
- **THEN** 叠加层 SHALL NOT 在两帧之间插值球员

#### Scenario: 预测超 TTL 隐藏

- **WHEN** `predicted_only` 球员的预测持续超过 TTL
- **THEN** 该球员 SHALL 从叠加层消失

### Requirement: view_scale_profiled 与 stale 淡化样式

视频叠加 HUD SHALL 支持 `bbox_source=view_scale_profiled` 的展示语义：以虚线框呈现（与 `last_good_bbox_reanchored` 的跨摄补全虚线族一致，可按来源微调透明度/标签），MUST NOT 伪装为真实 YOLO 检测实线框。前端 SHALL 在 `bbox_stale=true` 时淡化 bbox（如降低透明度/加"陈旧"标记），淡化程度 SHALL 基于后端提供的 `bbox_age_ms`（MUST NOT 前端自行估算）。`display_state` 存在时 SHALL 用于视觉语义（如 `REAL_BOX` 实线、`PROJECTED_BOX` 虚线、`PROJECTED_POINT` 光圈）。

#### Scenario: scale profile 虚线框

- **WHEN** overlay entity 的 `bbox_source == "view_scale_profiled"`
- **THEN** 前端 SHALL 以虚线框渲染
- **AND** 可显示来源标签（如"尺度投影"）区分于真实检测

#### Scenario: stale bbox 淡化

- **WHEN** overlay entity 的 `bbox_stale == true` 且存在 `bbox_age_ms`
- **THEN** 前端 SHALL 淡化该 bbox
- **AND** 淡化程度 SHALL 基于 `bbox_age_ms`（不自行估算）

#### Scenario: 旧枚举兼容

- **WHEN** overlay entity 的 `bbox_source` 为既有值（`last_good_bbox_reanchored` / `none`）或缺失，或 `display_state/bbox_stale/bbox_age_ms` 缺失
- **THEN** 前端 SHALL 按既有样式渲染
- **AND** SHALL NOT 因新枚举值或新字段缺失破坏解析

### Requirement: Renderer 消费 display_state 作为几何展示权威

前端人物 Overlay renderer SHALL 将 `display_state`（`REAL_BOX / ASSISTED_BOX / PROJECTED_BOX / PROJECTED_POINT / PREDICTED_POINT / HIDDEN`）作为人物几何形态（BOX / POINT / HIDDEN）的权威输入，MUST NOT 仅依赖 `evidence_type` 判断框 / 点 / 隐藏。`display_state` 存在时 SHALL 优先于 `evidence_type` 决定 geometry topology；`evidence_type` 仅决定 provenance style，MUST NOT 改变 identity hue。

#### Scenario: display_state 覆盖几何形态

- **WHEN** overlay entity 的 `display_state` 为 `PROJECTED_BOX`（真实 bbox 丢失后经迟滞降级，复用最后可靠 presentation box geometry），而同一 tick 的 `evidence_type` 为 `cross_view_projected`
- **THEN** renderer SHALL 按 `display_state` 渲染为 BOX 形态
- **AND** SHALL 按 `evidence_type` 以虚线 / 透明度表达 provenance

#### Scenario: display_state HIDDEN 不渲染

- **WHEN** overlay entity 的 `display_state` 为 `HIDDEN`
- **THEN** renderer SHALL 不渲染该球员

#### Scenario: 旧产物缺失 display_state 兼容

- **WHEN** 历史 fused overlay entity 缺失 `display_state`
- **THEN** renderer SHALL 按既有逻辑推导 legacy display_state（由 `evidence_type + bbox + footpoint` 得出）
- **AND** SHALL NOT 因字段缺失破坏解析

### Requirement: 展示几何状态与证据来源正交

Renderer MUST 使用 `display_state` 决定 BOX / POINT / HIDDEN topology，并使用 `evidence_type` 表达 provenance；两者 MUST NOT 相互重写。`player_id` SHALL 是 identity hue 的唯一 authority。`REAL_BOX` / `ASSISTED_BOX` SHALL 仅在当前 tick 存在对应真实 target-view bbox 时才为合法状态；当真实 bbox 丢失但仍有合法 presentation box 时，`display_state` SHALL 立即降级为 `PROJECTED_BOX`（复用最后可靠 presentation geometry），MUST NOT 继续输出 `REAL_BOX`。

#### Scenario: 真实 bbox 缺失不得保留 REAL_BOX

- **WHEN** `base_observed` 真实 bbox 在当前 tick 丢失，但有 donor / global projected evidence
- **THEN** `display_state` SHALL 立即变为 `PROJECTED_BOX`（复用最后可靠 presentation geometry）
- **AND** SHALL NOT 输出 `REAL_BOX`（`REAL_BOX` 仅表示当前存在真实 bbox）

#### Scenario: 三通道正交

- **WHEN** renderer 渲染一个 overlay entity
- **THEN** `player_id` SHALL 决定 identity hue、`display_state` SHALL 决定 topology、`evidence_type` SHALL 决定 provenance style
- **AND** 三者 MUST NOT 相互重写

