# auto-rally-playback-cues Specification

## Purpose

定义片段回放面上自动回合提示的两项能力：播放头进入新自动回合时在画面正中央叠加一次「第X回合」并自动淡出，以及把自动回合区间与其余区间以两种颜色映射到播放进度条并保留已播放读数；同时固定其数据范围为当前已发布切分 run 的 active algorithm Rally、序号取自片段自身的 `ordinal`、能力按数据可选启用且不改变其它调用方。
## Requirements
### Requirement: 自动回合回放提示的数据范围

片段回放面上的回合提示 SHALL 只消费当前已发布切分 run 的 active algorithm Rally，MUST NOT 混入人工片段、人工关键事件或已被替代的片段。

#### Scenario: 只使用当前已发布 run 的自动 Rally

- **WHEN** CaptureTake 存在已发布的正式切分结果
- **THEN** 系统 SHALL 使用 `source=algorithm`、`segmentation_run_id` 等于该 run、且 `edit_status=active` 的片段作为回放提示的唯一数据来源
- **AND** 提示与配色 SHALL NOT 使用其它 run 的自动片段

#### Scenario: 切分结果不可用时不做提示

- **WHEN** 正式切分摘要不可用，或其 `run_id` 为空
- **THEN** 系统 SHALL NOT 显示中央回合叠加提示
- **AND** 进度条 SHALL 保持启用区间配色之前的渲染外观

#### Scenario: 自动回合数量为零时不做提示

- **WHEN** 存在有效 `run_id`，但该 run 的 active algorithm Rally 数量为 0
- **THEN** 系统 SHALL NOT 显示中央回合叠加提示
- **AND** 进度条 SHALL NOT 被整体涂成「非回合」色

#### Scenario: 不受片段列表筛选影响

- **WHEN** 用户切换片段列表的筛选类别
- **THEN** 用于中央提示与进度条配色的自动回合集合 SHALL 保持不变

#### Scenario: 不纳入人工来源

- **WHEN** CaptureTake 存在现场人工片段或人工关键事件
- **THEN** 系统 SHALL NOT 因播放头进入这些区间而显示中央提示
- **AND** 进度条配色 SHALL NOT 把这些区间标记为自动回合区间

#### Scenario: 回合序号取自切分结果

- **WHEN** 显示回合序号
- **THEN** 系统 SHALL 使用该 Rally 自身的 `ordinal`
- **AND** SHALL NOT 按列表筛选后的位置或播放先后重新编号

#### Scenario: 区间边界与归属口径

- **WHEN** 计算某个自动回合的时间区间
- **THEN** 起点 SHALL 取 `effective_start_ms`（缺省时取 `start_ms`），终点 SHALL 取 `effective_end_ms`（缺省时取 `end_ms`，再缺省时取媒体总时长）
- **AND** 播放头归属判定 SHALL 使用左闭右开区间 `[起点, 终点)`

### Requirement: 播放头进入自动回合时的中央叠加提示

播放器 SHALL 在播放头所属自动回合发生变化时，于视频画面正中央叠加显示一次回合序号，并在短暂停留后自动淡出。

#### Scenario: 跨入新回合时提示一次

- **WHEN** 播放头所属的自动回合从无变为某个回合，或从一个回合变为另一个回合
- **THEN** 播放器 SHALL 在视频画面正中央叠加显示「第X回合」，X 为该回合的 `ordinal`
- **AND** 在同一回合内持续播放期间 SHALL NOT 重复显示

#### Scenario: 自动淡出

- **WHEN** 中央叠加提示已显示并经过约 2 秒
- **THEN** 提示 SHALL 自动淡出
- **AND** 淡出 SHALL NOT 改变播放状态、播放位置或选中片段

#### Scenario: 暂停与定位同样触发

- **WHEN** 视频处于暂停状态，用户通过拖动进度条或点击片段行使播放头进入另一个自动回合
- **THEN** 播放器 SHALL 同样显示一次该回合的中央提示

#### Scenario: 离开全部自动回合

- **WHEN** 播放头离开全部自动回合区间
- **THEN** 播放器 SHALL NOT 显示中央叠加提示
- **AND** 提示状态 SHALL 重置，使再次进入同一回合时仍会提示一次

#### Scenario: 不遮挡播放器交互

- **WHEN** 中央叠加提示可见
- **THEN** 叠加层 SHALL NOT 接收指针事件
- **AND** 播放/暂停、逐帧前进后退、进度条拖动与键盘快捷键 SHALL 保持可用

#### Scenario: 提示文字保持可读

- **WHEN** 中央叠加提示显示在明亮或高对比的实时画面上
- **THEN** 文字 SHALL 采用高不透明度前景色并配合深色描边
- **AND** SHALL NOT 采用低对比的半透明水印式呈现

### Requirement: 播放进度条的自动回合区间配色

播放器 SHALL 把自动回合区间与其余区间以两种颜色映射到播放进度条上，并在启用配色时保留既有的已播放读数与拖动定位行为。

#### Scenario: 两种颜色区分区间结构

- **WHEN** 进度条启用自动回合区间配色
- **THEN** 自动回合区间与自动回合之外的区间 SHALL 使用两种不同颜色
- **AND** 配色 SHALL 覆盖整条可播放时长，包括首个回合之前与末个回合之后的区间

#### Scenario: 按媒体总时长归一化

- **WHEN** 媒体总时长可用
- **THEN** 各区间在进度条上的左偏移与宽度 SHALL 按 `区间时间 / 媒体总时长` 归一化
- **AND** 归一化基准 SHALL 与进度条取值的上界一致

#### Scenario: 保留已播放与未播放读数

- **WHEN** 进度条启用区间配色
- **THEN** 已播放部分 SHALL 以区别于两种区间颜色的表现形式叠加呈现
- **AND** 用户 SHALL 仍能区分已播放区间与未播放区间

#### Scenario: 保留拖动定位行为

- **WHEN** 用户在启用配色后的进度条上拖动
- **THEN** 系统 SHALL 触发与启用前一致的 seek 行为
- **AND** SHALL NOT 因配色改变进度条的可用性与禁用条件

#### Scenario: 时长不可用时不着色

- **WHEN** 媒体总时长不可用或为 0
- **THEN** 系统 SHALL NOT 渲染区间配色
- **AND** 进度条 SHALL 保持启用前的渲染外观与禁用行为

#### Scenario: 越界与退化区间

- **WHEN** 某个自动回合区间的起点早于 0、终点超出媒体总时长，或终点不晚于起点
- **THEN** 系统 SHALL 把越界区间裁剪到可播放范围内
- **AND** SHALL 丢弃裁剪后长度为零的退化区间
- **AND** SHALL NOT 因此中断其余区间的渲染

### Requirement: 回放提示按数据可选启用

回放提示能力 SHALL 以可选数据启用的方式实现，未提供自动回合数据的调用方 MUST NOT 观察到任何渲染或交互变化。

#### Scenario: 未传入自动回合数据

- **WHEN** 调用方不传入当前自动回合与自动回合区间
- **THEN** 播放器 SHALL NOT 渲染中央叠加层
- **AND** 进度条 SHALL NOT 附加区间配色样式，SHALL 保持其原生 `accent` 上色外观
- **AND** 其余 DOM 结构与交互行为 SHALL 与启用前一致

#### Scenario: 其它调用点不受影响

- **WHEN** 其它页面以不传自动回合数据的方式使用同一播放器组件
- **THEN** 这些页面的渲染与交互 SHALL 保持不变

#### Scenario: 隔离复核模式不启用

- **WHEN** 片段页处于内部边界复核隔离模式
- **THEN** 系统 SHALL NOT 显示中央回合叠加提示
- **AND** SHALL NOT 启用进度条区间配色
- **AND** 既有复核操作 SHALL 不受影响

#### Scenario: 保持只读回放约束

- **WHEN** 回放提示与区间配色生效
- **THEN** 页面 SHALL NOT 发送 Segment PATCH、边界复核决定或 AnalysisBatch 创建请求
- **AND** SHALL NOT 用本地状态修改任何 `CaptureSegment` 边界

