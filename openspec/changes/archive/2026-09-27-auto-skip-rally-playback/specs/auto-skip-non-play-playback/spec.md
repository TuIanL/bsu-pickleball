## MODIFIED Requirements

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
- **THEN** 新的取值 SHALL 作用于此后发起的播放起点解析和片段播放结束判定
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

### Requirement: 开启自动跳过时的续播与停止

当自动跳过开关开启时，系统 SHALL 在用户发起播放时从播放头所在的自动回合或其后的最近自动回合开始播放；并在片段自然播放到有效终点后继续播放下一个比赛时间区间，在不存在下一个区间时停止。

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

#### Scenario: 从回合内部的播放头开始

- **WHEN** 开关开启，播放头位于当前正式 run 的某个 active algorithm 回合内部，且用户发起播放
- **THEN** 系统 SHALL 从当前播放头继续播放到该回合的有效终点
- **AND** 自然播完后 SHALL 按下一个区间的选取规则继续播放

#### Scenario: 从首回合之前或回合间隙开始

- **WHEN** 开关开启，播放头位于首个回合之前或两个回合之间，且用户发起播放
- **THEN** 系统 SHALL 定位到起点不早于播放头的首个 active algorithm 回合并开始播放
- **AND** SHALL 跳过播放头与该回合起点之间的非比赛时间

#### Scenario: 末回合之后发起播放

- **WHEN** 开关开启，播放头位于最后一个 active algorithm 回合之后，且不存在后续回合
- **THEN** 系统 SHALL 保持暂停
- **AND** SHALL NOT 播放末回合之后的非比赛时间

### Requirement: 弱约束下的拖动与逐帧边界

自动跳过开启时，系统 SHALL NOT 限制用户对播放位置的自由控制；拖动或逐帧 SHALL NOT 直接触发自动续播；用户之后显式发起播放时，系统 MUST 按开启自动跳过时的回合选择规则处理当前播放头。

#### Scenario: 拖动仍可自由定位

- **WHEN** 开关开启且用户拖动播放进度条或时间线
- **THEN** 播放头 SHALL 停在用户指定的位置，包括非比赛时间区间
- **AND** SHALL NOT 被强制移回最近的比赛时间区间

#### Scenario: 拖动中断不触发续播

- **WHEN** 某个区间正在播放期间，用户拖动播放位置或跳转到别处
- **THEN** 该区间 SHALL 被视为被中断而非被播完
- **AND** SHALL NOT 因该次中断自动续播到下一个区间

#### Scenario: 定位到非比赛时间后发起播放

- **WHEN** 开关开启，用户将播放头定位到非比赛时间并显式发起播放
- **THEN** 若后续存在 active algorithm 回合，系统 SHALL 跳到起点不早于当前播放头的首个回合并播放
- **AND** 若后续不存在回合，系统 SHALL 保持暂停
- **AND** 定位操作本身 SHALL 保持在用户指定位置，直到用户发起播放

#### Scenario: 关闭自动跳过时从定位处播放

- **WHEN** 开关关闭，用户将播放头定位到非比赛时间并发起播放
- **THEN** 播放器 SHALL 从用户指定位置按既有行为播放
- **AND** SHALL NOT 自动跳到后续比赛时间区间

#### Scenario: 逐帧越过区间终点不算播完

- **WHEN** 开关开启且用户逐帧前进越过当前区间的有效终点
- **THEN** 该区间 SHALL 被视为被中断而非被播完
- **AND** SHALL NOT 触发自动续播
