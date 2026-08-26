## MODIFIED Requirements

### Requirement: 同步显示球员移动轨迹

系统 SHALL 按视频当前播放时间显示稳定球员身份的当前位置和时间尾迹。每名球员 SHALL 使用稳定的视觉颜色和 `P1` 至 `P4` 标签；视频人物框、小地图球员点与小地图球员尾迹对同一 canonical `player_id` MUST 使用相同的 identity hue，且颜色不得依赖当前排序、可见人数、局部 track ID、render slot 或 evidence 来源。尾迹 SHALL 表达时间方向，当前位置 SHALL 具有明显的焦点标记，且相邻轨迹点存在足够时间缺口或位移超过断线阈值时 MUST 断线。

#### Scenario: 四名球员轨迹可用

- **WHEN** 当前时间窗口包含四名稳定球员的有效 `court_point`
- **THEN** HUD 显示四条相互可区分的球员尾迹、当前位置和身份标签，不显示原始 detector `track_id`

#### Scenario: 视频与小地图身份颜色一致

- **WHEN** 同一 canonical `Player_1` 至 `Player_4` 同时显示在视频人物框和小地图中
- **THEN** 该球员在两处 SHALL 使用相同 identity hue
- **AND** 某名其他球员暂时缺失、排序变化或切换 evidence type 时，其余球员颜色 SHALL 保持不变

#### Scenario: 球员轨迹存在缺口

- **WHEN** 同一球员相邻有效点之间的 timestamp 差超过轨迹连接阈值
- **THEN** HUD 将轨迹拆成多个片段，不绘制跨越缺口的直线，并保留最近有效位置的状态

#### Scenario: 球员轨迹存在大位移跳变

- **WHEN** 同一球员相邻有效点的球场位移超过断线阈值（默认 6 英尺，可配置）
- **THEN** HUD 将轨迹拆成多个片段，不绘制跨越跳变的直线，避免出现连接两个不相关位置的虚假连线

#### Scenario: 当前窗口没有球员点

- **WHEN** 当前播放时间附近没有任何有效球员投影点
- **THEN** HUD 隐藏过期当前位置，显示“当前时间无有效球员投影”或等价降级状态，不显示静态模拟球员

### Requirement: 显示球的图像轨迹、平面投影和弹跳候选

系统 SHALL 将球轨迹按空间语义分层显示：视频主画面使用当前展示机位的 `image_xy` 表达图像中的球路，小地图使用同一 canonical tick 下的 `court_xy` 或展示合格重建 segment 的 canonical court-space 坐标表达球场平面投影；弹跳候选 SHALL 使用独立 marker。重建球路存在且具备可展示 court-space 样本时，小地图 SHALL 优先使用该重建球路；重建球路不可用或无可展示 court-space 样本时，系统 SHALL 保留旧 `BallTrajectoryArtifact` 的有效 `court_xy` 回退。系统 SHALL 区分检测点、插值点和低置信度候选的视觉强度或线型，并不得将 image-space 坐标当作小地图场地坐标。

#### Scenario: 旧球轨迹可用

- **WHEN** 当前真实任务包含带有效 `image_xy` 和 `court_xy` 的旧球轨迹样本，且没有可展示的重建球路
- **THEN** 视频中显示高对比度渐隐球路和当前球点，小地图中显示可同步的球场平面投影，并在状态摘要中显示球层可用

#### Scenario: 重建球路可用

- **WHEN** 当前真实任务包含通过展示资格检查的重建球路 segment，且该 segment 有当前 canonical tick 可用的 court-space 样本
- **THEN** 视频 SHALL 使用当前展示机位的 image-space 路径
- **AND** 小地图 SHALL 在同一 tick 使用该 segment 的 canonical court-space 路径
- **AND** 小地图不得因旧 `BallTrajectoryArtifact` 缺失而隐藏该球路

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
