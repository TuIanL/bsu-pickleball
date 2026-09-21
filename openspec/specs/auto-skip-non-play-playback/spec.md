# auto-skip-non-play-playback Specification

## Purpose
TBD - created by archiving change add-auto-skip-non-play-playback. Update Purpose after archive.
## Requirements
### Requirement: 自动跳过非比赛时间开关

片段页 SHALL 提供一个控制是否自动跳过非比赛时间的开关，其默认状态为开启，并在数据不可用时显式降级而不是静默无效。

#### Scenario: 默认开启

- **WHEN** 用户打开普通片段页
- **THEN** 自动跳过开关 SHALL 处于开启状态
- **AND** SHALL 不因此改变页面其它控件或列表的呈现

#### Scenario: 用户关闭后恢复既有行为

- **WHEN** 用户关闭该开关
- **THEN** 片段播放 SHALL 恢复为播放到有效终点后自动暂停
- **AND** 该开关状态 SHALL NOT 被持久化到下次进入页面

#### Scenario: 切换即时生效

- **WHEN** 用户在任何时刻切换该开关
- **THEN** 新的取值 SHALL 作用于此后发生的片段播放结束判定
- **AND** SHALL NOT 改变当前正在播放的位置、播放状态或选中片段

#### Scenario: 无正式切分结果时不可用

- **WHEN** 该 CaptureTake 没有已发布的正式切分结果，或不存在任何 active algorithm 回合
- **THEN** 开关 SHALL 处于不可用状态
- **AND** SHALL 给出明确的原因说明
- **AND** SHALL NOT 让页面其余能力受影响

#### Scenario: 隔离复核模式不启用

- **WHEN** 片段页处于内部边界复核隔离模式
- **THEN** 该开关 SHALL NOT 出现在界面上
- **AND** 播放 SHALL 保持复核所需的「播到有效终点自动暂停」行为
- **AND** 既有复核操作 SHALL 不受影响

### Requirement: 非比赛时间的推导口径

系统 SHALL 把「非比赛时间」定义为当前已发布切分 run 的 active algorithm 回合区间之外的剩余时间，MUST NOT 引入新的数据来源或后端接口。

#### Scenario: 以 algorithm 回合为唯一基准

- **WHEN** 推导将被跳过的区间
- **THEN** 基准 SHALL 为当前已发布 run 的 active algorithm 回合区间
- **AND** 起点 SHALL 取 `effective_start_ms`（缺省时取 `start_ms`），终点 SHALL 取 `effective_end_ms`（缺省时取 `end_ms`）

#### Scenario: 补集覆盖时间轴两端

- **WHEN** 第一个回合的起点晚于 0，或最后一个回合的终点早于媒体总时长
- **THEN** 这两段剩余时间 SHALL 同样被视为非比赛时间

#### Scenario: 不受片段列表筛选影响

- **WHEN** 用户切换片段列表的筛选类别
- **THEN** 将被跳过的区间集合 SHALL 保持不变

#### Scenario: 不纳入人工来源

- **WHEN** CaptureTake 存在现场人工片段
- **THEN** 它们 SHALL NOT 被当作可续播的比赛时间区间
- **AND** SHALL NOT 改变非比赛时间的推导结果

#### Scenario: 刻意不区分非比赛时间的成因

- **WHEN** 推导出某个非比赛区间
- **THEN** 系统 SHALL NOT 区分它是分间发球准备、暂停换边、模型未判定的区段，还是被最短时长规则压制的漏检回合
- **AND** 该区间 SHALL 一概参与跳过

### Requirement: 开启自动跳过时的续播与停止

当自动跳过开关开启时，系统 SHALL 在片段自然播放到有效终点后继续播放下一个比赛时间区间，并在不存在下一个区间时停止。

#### Scenario: 自然播完后续播到下一个区间

- **WHEN** 某区间自然播放到有效终点，且其后仍存在 algorithm 回合区间
- **THEN** 系统 SHALL 从下一个区间的起点继续播放
- **AND** SHALL 跳过两者之间的全部非比赛时间
- **AND** 播放模式 SHALL 保持为片段播放，选中项 SHALL 跟随到新区间

#### Scenario: 末段播完后停止

- **WHEN** 最后一个 algorithm 回合区间自然播放到有效终点
- **THEN** 系统 SHALL 停在终点并暂停
- **AND** MUST NOT 循环回第一个区间

#### Scenario: 下一个区间的选取规则

- **WHEN** 确定续播目标
- **THEN** SHALL 取「起点不早于当前播放窗口结束时间」的第一个 algorithm 回合区间
- **AND** SHALL NOT 按当前片段的数组下标递推，以保证从人工片段起点出发时同样有定义

#### Scenario: 关闭时不续播

- **WHEN** 开关关闭且某区间自然播放到有效终点
- **THEN** 系统 SHALL 自动暂停并清除片段播放模式
- **AND** SHALL NOT 继续播放到下一个区间

### Requirement: 弱约束下的拖动与逐帧边界

自动跳过开启时，系统 SHALL NOT 限制用户对播放位置的自由控制；续播 MUST 只由片段自然播完触发。

#### Scenario: 拖动仍可自由定位

- **WHEN** 开关开启且用户拖动播放进度条或时间线
- **THEN** 播放头 SHALL 停在用户指定的位置，包括非比赛时间区间
- **AND** SHALL NOT 被强制移回最近的比赛时间区间

#### Scenario: 拖动中断不触发续播

- **WHEN** 某个区间正在播放期间，用户拖动播放位置或跳转到别处
- **THEN** 该区间 SHALL 被视为被中断而非被播完
- **AND** SHALL NOT 触发续播到下一个区间

#### Scenario: 手动进入非比赛区间后播放不会自动跳走

- **WHEN** 用户将播放头置于非比赛时间区间并开始播放
- **THEN** 播放器 SHALL 继续播放该处内容，不自动跳转到下一个比赛时间区间

#### Scenario: 逐帧越过区间终点不算播完

- **WHEN** 开关开启且用户逐帧前进越过当前区间的有效终点
- **THEN** 该区间 SHALL 被视为被中断而非被播完
- **AND** SHALL NOT 触发续播

### Requirement: 自动续播引起的中央回合提示合并

由自动续播引起的连续回合变化 SHALL 合并为同一块中央提示，MUST NOT 在短时间内出现两次独立的淡入淡出。

#### Scenario: 提示显示窗口内只更新文字

- **WHEN** 中央回合提示正处于显示窗口内，且播放头所属回合发生变化
- **THEN** 提示 SHALL 就地更新为最新回合的序号
- **AND** SHALL NOT 重新触发淡入、SHALL NOT 延长显示窗口

#### Scenario: 独立淡入之间受最小静默间隔约束

- **WHEN** 上一次中央提示已淡出，且自动续播在最小静默间隔内再次引起回合变化
- **THEN** 系统 SHALL NOT 开启新的提示窗口
- **AND** 直到静默间隔满足后才允许再次提示

#### Scenario: 用户主动导航不受节流

- **WHEN** 用户主动点击片段行或拖动播放位置使播放头进入另一个回合
- **THEN** 系统 SHALL 立即显示该回合的中央提示
- **AND** SHALL NOT 因最小静默间隔而抑制该提示

#### Scenario: 既有提示行为不被改变

- **WHEN** 提示显示、淡出与不遮挡播放器交互
- **THEN** 其触发条件、显示时长与淡出行为 SHALL 与自动跳过能力引入前一致

