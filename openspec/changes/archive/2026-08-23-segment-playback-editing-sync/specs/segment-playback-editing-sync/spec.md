## ADDED Requirements

### Requirement: 统一片段回放状态

系统 SHALL 由片段管理页协调当前播放时间、媒体时长、当前片段 ID 和片段播放模式，并将这些状态同步给片段列表与时间线。

#### Scenario: 播放器时间更新

- **WHEN** 播放器触发时间更新
- **THEN** 页面 SHALL 更新当前播放时间
- **AND** 时间线播放头 SHALL 使用同一个当前播放时间
- **AND** 当前有效区间包含该时间的片段 SHALL 被标记为 active

#### Scenario: 媒体时长加载

- **WHEN** 播放器加载媒体元数据并取得时长
- **THEN** 页面 SHALL 更新时间线的可用总时长
- **AND** 时间线 SHALL 不再使用固定的 0 作为播放头位置

### Requirement: 点击片段播放有效区间

系统 SHALL 支持用户点击一个可播放片段后从其有效起点开始播放，并将片段的有效终点作为本次播放的停止边界。

#### Scenario: 点击 rally 片段

- **WHEN** 用户点击右侧片段行的播放区域
- **THEN** 播放器 SHALL 定位到 `corrected_start_ms`（不存在时使用 `start_ms`）
- **AND** 播放器 SHALL 自动开始播放
- **AND** 该片段 SHALL 立即高亮

#### Scenario: 片段没有 corrected 边界

- **WHEN** 片段没有边界修正值
- **THEN** 播放 SHALL 使用原始 `start_ms` 和 `end_ms`

#### Scenario: 标签编辑不触发播放

- **WHEN** 用户双击片段标签或进入标签输入框
- **THEN** 系统 SHALL 进入标签编辑
- **AND** SHALL 不因编辑入口的 click/double-click 触发片段播放或改变当前播放位置

### Requirement: 片段播放完成后自动暂停

系统 SHALL 在片段播放到有效终点时自动暂停，并清除一次性片段播放模式。

#### Scenario: 播放到片段终点

- **WHEN** 当前时间达到或超过片段有效终点
- **THEN** 播放器 SHALL 将时间钳制到有效终点附近
- **AND** SHALL 自动暂停
- **AND** 页面 SHALL 保留该片段的选中/高亮状态但标记为未播放

#### Scenario: 视频先自然结束

- **WHEN** 媒体在片段终点检查前触发 `ended`
- **THEN** 系统 SHALL 自动暂停并清除片段播放模式
- **AND** SHALL 不继续播放到下一个片段

### Requirement: 列表、时间线和事件标记联动

系统 SHALL 让片段列表、片段块、播放头和关键事件标记使用同一时间坐标和片段 ID。

#### Scenario: 点击时间线片段块

- **WHEN** 用户点击时间线中的片段块
- **THEN** 播放器 SHALL seek 到该片段有效起点
- **AND** 对应列表行 SHALL 高亮
- **AND** 该操作 SHALL 不自动修改片段边界或关键事件

#### Scenario: 点击时间线空白区域

- **WHEN** 用户点击没有片段块的时间线位置
- **THEN** 播放器 SHALL seek 到该时间
- **AND** 播放头 SHALL 移动到该位置
- **AND** 当前列表高亮 SHALL 清除或按当前所在有效区间更新

#### Scenario: 播放经过关键事件

- **WHEN** 当前播放时间经过 `SessionTimelineEvent.timestamp_ms`
- **THEN** 事件标记 SHALL 保持其原始时间位置
- **AND** 事件标记 SHALL 不因片段播放或边界编辑被移动、删除或重建

### Requirement: 边界拖拽使用本地草稿并在释放时提交

系统 SHALL 将时间线边界拖拽视为对 `CaptureSegment` 有效边界的编辑；拖拽移动期间只更新本地预览，释放后最多提交一次持久化修改。

#### Scenario: 拖拽起点或终点

- **WHEN** 用户拖拽一个 active、非 open、非 superseded 片段的边界
- **THEN** 时间线 SHALL 即时展示本地边界预览
- **AND** 拖拽移动期间 SHALL 不发送 PATCH 请求
- **AND** 释放指针后 SHALL 提交 `corrected_start_ms`、`corrected_end_ms` 和 `expected_version`

#### Scenario: 边界保存成功

- **WHEN** 释放拖拽后 PATCH 成功
- **THEN** 页面 SHALL 使用服务端返回的片段和新 `edit_version` 更新列表与时间线
- **AND** 播放、列表和时间线 SHALL 继续使用新的有效边界

#### Scenario: 边界保存失败

- **WHEN** 边界 PATCH 失败
- **THEN** 页面 SHALL 恢复拖拽前的边界
- **AND** SHALL 显示保存失败原因
- **AND** SHALL 不把未确认的本地草稿用于创建分析批次

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
