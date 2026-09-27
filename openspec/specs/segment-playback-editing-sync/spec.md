# segment-playback-editing-sync Specification

## Purpose

定义片段回放与边界编辑的联动：统一的回放状态、列表/时间线/事件标记联动、有效区间播放与结束自动暂停、边界拖拽的本地草稿与释放提交，以及边界校验与并发保护。
## Requirements
### Requirement: 统一片段回放状态

系统 SHALL 由数据分析视图协调当前播放时间、媒体时长、当前回合 ID 和回合窗口播放模式，并将这些状态同步给片段面板列表。

#### Scenario: 播放器时间更新

- **WHEN** 播放器触发时间更新
- **THEN** 页面 SHALL 更新当前播放时间
- **AND** 当前有效区间包含该时间的回合 SHALL 在片段面板中被标记为 active

#### Scenario: 媒体时长加载

- **WHEN** 播放器加载媒体元数据并取得时长
- **THEN** 页面 SHALL 更新回合窗口解析可用的总时长
- **AND** 回合命中判定 SHALL NOT 使用固定的 0 作为播放头位置

### Requirement: 点击片段播放有效区间

系统 SHALL 支持用户在片段面板点击一个可播放回合后从其有效起点开始播放，并将回合的有效终点作为本次播放的停止边界。

#### Scenario: 点击 rally 片段

- **WHEN** 用户点击片段面板模型回合列表中的回合行
- **THEN** 播放器 SHALL 定位到 `effective_start_ms`（不存在时使用 `start_ms`）
- **AND** 播放器 SHALL 自动开始播放
- **AND** 该回合 SHALL 立即高亮

#### Scenario: 片段没有 corrected 边界

- **WHEN** 片段没有边界修正值
- **THEN** 播放 SHALL 使用原始 `start_ms` 和 `end_ms`

### Requirement: 片段播放完成后自动暂停

系统 SHALL 在回合窗口自然播放到有效终点时结束本次回合播放并清除一次性回合播放模式；自动跳过开关关闭时 SHALL 自动暂停，开启时 SHALL 续播到下一个比赛时间区间，且没有下一个区间时停在终点。

#### Scenario: 关闭自动跳过后播放到片段终点

- **WHEN** 自动跳过开关关闭，且当前时间达到或超过回合有效终点
- **THEN** 播放器 SHALL 将时间钳制到有效终点附近
- **AND** SHALL 自动暂停
- **AND** 页面 SHALL 保留该回合的选中/高亮状态但标记为未播放

#### Scenario: 开启自动跳过后播放到片段终点

- **WHEN** 自动跳过开关开启，当前时间达到或超过回合有效终点，且其后仍存在 algorithm 回合区间
- **THEN** 播放器 SHALL 将时间钳制到有效终点附近
- **AND** SHALL 从下一个区间的起点继续播放，并跳过两者之间的非比赛时间
- **AND** 页面 SHALL 保持回合播放模式并将选中项更新为新区间

#### Scenario: 开启自动跳过后没有下一个区间

- **WHEN** 自动跳过开关开启，且最后一个 algorithm 回合区间到达有效终点
- **THEN** 播放器 SHALL 停在终点并自动暂停
- **AND** MUST NOT 循环回第一个区间

#### Scenario: 被中断的播放不算播完

- **WHEN** 回合播放期间用户拖动播放位置或逐帧越过有效终点，或系统 seek 到别处
- **THEN** 该次播放 SHALL 被视为被中断
- **AND** SHALL NOT 触发续播到下一个区间

#### Scenario: 视频先自然结束

- **WHEN** 媒体在回合终点检查前触发 `ended`
- **THEN** 系统 SHALL 自动暂停并清除回合播放模式
- **AND** SHALL 不继续播放到下一个回合





### Requirement: 边界校验与并发保护

系统 SHALL 在服务层拒绝无效片段边界，并使用编辑版本保护并发修改。

#### Scenario: 无效边界

- **WHEN** 请求提交负数、结束早于开始、超过可用媒体范围或短于最小片段时长的边界
- **THEN** API SHALL 返回稳定的 400 错误
- **AND** SHALL 不修改 corrected 边界和 `edit_version`

#### Scenario: 编辑版本冲突

- **WHEN** 请求携带的 `expected_version` 与服务端当前 `edit_version` 不一致
- **THEN** API SHALL 返回 409
- **AND** SHALL 不覆盖服务端较新的边界

#### Scenario: 片段编辑与关键事件隔离

- **WHEN** 边界 PATCH 成功
- **THEN** 系统 SHALL 只写入 `CaptureSegment` 及其编辑操作记录
- **AND** SHALL 保持该 CaptureTake 的 `SessionTimelineEvent` 内容和 ID 不变

