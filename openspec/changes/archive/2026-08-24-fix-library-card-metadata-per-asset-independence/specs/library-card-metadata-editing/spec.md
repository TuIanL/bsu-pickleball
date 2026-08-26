# library-card-metadata-editing (delta)

## MODIFIED Requirements

### Requirement: 每素材独立真源写入

标题/日期保存 SHALL 按素材类型写入**各自的** `display_*` 真源，且同场次下的不同素材 SHALL 互不牵连：`upload` 写入 `video` 自身的 `display_title` / `display_date`；`recording` 写入 `RecordingSession` 自身的 `display_title` / `display_date`；`sync_recording` 写入 `SyncRecordingSession` 自身的 `display_title` / `display_date`。系统 SHALL NOT 把有 `fieldSessionId` 的素材写入所属 `FieldSession.title` / `FieldSession.started_at`。

#### Scenario: upload 素材改 video 自身
- **WHEN** 用户编辑一个 `upload` 素材的标题或日期
- **THEN** 系统 SHALL PATCH `/api/videos/{id}` 写入 `display_title` / `display_date`
- **AND** SHALL NOT 修改系统 `uploaded_at`（上传时间保留只读）

#### Scenario: recording 素材改 RecordingSession 自身
- **WHEN** 用户编辑一个 `recording` 素材的标题或日期（无论是否有 `fieldSessionId`）
- **THEN** 系统 SHALL PATCH `/api/recordings/{id}` 写入 `display_title` / `display_date`
- **AND** SHALL NOT PATCH `/api/field-sessions/{id}`

#### Scenario: sync_recording 素材改 SyncRecordingSession  * 自身
- **WHEN** 用户编辑一个 `sync_recording` 素材的标题或日期（无论是否有 `fieldSessionId`）
- **THEN** 系统 SHALL PATCH `/api/sync-recordings/{id}` 写入 `display_title` / `display_date`
- **AND** SHALL NOT PATCH `/api/field-sessions/{id}`

#### Scenario: 同场次多卡互不牵连
- **WHEN** 用户在同一 `FieldSession` 分组下的素材 A、B 分别编辑标题/日期
- **THEN** A 的展示值 SHALL 仅反映 A 自身的 `display_*`
- **AND** B 的展示值 SHALL 仅反映 B 自身的 `display_*`，不因 A 的编辑而变化

#### Scenario: 保存后局部刷新
- **WHEN** 标题/日期保存成功
- **THEN** 系统 SHALL 定向重投影该素材（局部刷新），不重建全库列表
- **AND** 自定义名称 SHALL 立即可被列表搜索匹配
