# library-semantic-metadata (delta)

## MODIFIED Requirements

### Requirement: 语义化标题解析

LibraryItem 的展示标题 SHALL 按优先级解析为语义化命名，且用户可编辑的覆盖值具有最高优先级；`court_name` 仅作为次要 metadata，不得再作为用户可见主标题。覆盖值 SHALL 仅源自素材自身（`video` / `RecordingSession` / `SyncRecordingSession` 的 `display_title`），SHALL NOT 回退到所属 `FieldSession.title`。

#### Scenario: 用户可编辑覆盖值最高优先
- **WHEN** 素材存在用户编辑过的 `displayTitle`（或对应真源的 `display_title`）
- **THEN** 展示标题 SHALL 采用该用户覆盖值
- **AND** SHALL NOT 回退到 matchTitle / FieldSession 标题 / 时间+形式 / source id

#### Scenario: 有分析 metadata 优先用比赛标题
- **WHEN** 素材无用户覆盖值，且关联的 analysis metadata 提供 `matchTitle`
- **THEN** 展示标题 SHALL 采用该 match title
- **AND** 其次回退到「时间 + 比赛形式」，最后才用 raw source id
- **AND** SHALL NOT 回退到 `FieldSession.title`

#### Scenario: 标题与 courtName 去重
- **WHEN** 卡片同时展示标题与场地名称
- **THEN** 同一值不得在两处重复出现

#### Scenario: 日期解析同样支持用户覆盖
- **WHEN** 素材存在用户编辑过的 `displayDate`（或对应真源的 `display_date`）
- **THEN** 卡片日期 SHALL 采用该用户覆盖值
- **AND** SHALL NOT 回退到 `FieldSession.started_at`
- **AND** 缺失时回退到录制开始时间 / 上传时间派生值
