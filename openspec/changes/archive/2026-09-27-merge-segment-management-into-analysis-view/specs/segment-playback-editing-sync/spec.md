# segment-playback-editing-sync Delta

## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: 列表、时间线和事件标记联动

**Reason**: 片段管理页的 `EditableSegmentTimeline`（回合块时间线与关键事件标记联动）随页面删除；数据分析视图的定位由片段面板列表与主画面播放器进度条承担。

**Migration**: 回合定位 → 片段面板点击与播放器进度条；`SessionTimelineEvent` 数据与后端契约保留（`session-timeline-events`），无前端展示迁移。

### Requirement: 边界拖拽使用本地草稿并在释放时提交

**Reason**: QA 复核与边界编辑前端整体删除（产品决策：切分结果前端完全只读）；后端 PATCH 契约（`segment-editing`，含乐观锁）保留。

**Migration**: 无前端替代。若未来恢复边界复核流程，需重建前端并重新立 spec。
