# auto-skip-non-play-playback Delta

## MODIFIED Requirements

### Requirement: 自动跳过非比赛时间开关

数据分析视图 SHALL 提供一个控制是否自动跳过非比赛时间的开关，其默认状态为开启，并在数据不可用时显式降级而不是静默无效。

#### Scenario: 默认开启

- **WHEN** 用户打开数据分析视图
- **THEN** 自动跳过开关 SHALL 处于开启状态
- **AND** SHALL 不因此改变页面其它控件或面板列表的呈现

#### Scenario: 用户关闭后恢复既有行为

- **WHEN** 用户关闭该开关
- **THEN** 播放 SHALL 恢复为播放到有效终点后自动暂停
- **AND** 该开关状态 SHALL NOT 被持久化到下次进入页面

#### Scenario: 切换即时生效

- **WHEN** 用户在任何时刻切换该开关
- **THEN** 新的取值 SHALL 作用于此后发起的播放起点解析和回合播放结束判定
- **AND** SHALL NOT 改变当前正在播放的位置、播放状态或选中回合

#### Scenario: 无正式切分结果时不可用

- **WHEN** 关联 CaptureTake 没有已发布的正式切分结果，或不存在任何 active algorithm 回合
- **THEN** 开关 SHALL 处于不可用状态
- **AND** SHALL 给出明确的原因说明
- **AND** SHALL NOT 让页面其余能力受影响

#### Scenario: 素材无片段数据关联时不可用

- **WHEN** 分析任务没有关联 CaptureTake（如上传视频）
- **THEN** 开关 SHALL 处于不可用状态并说明该分析不关联采集片段
- **AND** SHALL NOT 让视频播放、叠加层或报告入口受影响

### Requirement: 开启自动跳过时的续播与停止

当自动跳过开关开启时，系统 SHALL 在用户发起播放时从播放头所在的自动回合或其后的最近自动回合开始播放；并在回合窗口自然播放到有效终点后继续播放下一个比赛时间区间，在不存在下一个区间时停止。

#### Scenario: 自然播完后续播到下一个区间

- **WHEN** 某区间自然播放到有效终点，且其后仍存在 algorithm 回合区间
- **THEN** 系统 SHALL 从下一个区间的起点继续播放
- **AND** SHALL 跳过两者之间的全部非比赛时间
- **AND** 播放模式 SHALL 保持为回合窗口播放，选中项 SHALL 跟随到新区间

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
- **THEN** 系统 SHALL 自动暂停并清除回合窗口播放模式
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
