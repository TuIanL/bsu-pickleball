## ADDED Requirements

### Requirement: FieldSession 分组能力迁移至 Library
`recorded-task-grouping` 中「按 FieldSession 对 RecordingSession 分组」的资产组织能力 SHALL 从任务页迁移到比赛库，作为 Collection / Folder 组织方式，而非继续嵌在「录制视频任务」Tab。

#### Scenario: FieldSession 作为库文件夹
- **WHEN** 比赛库存在属于同一 FieldSession 的若干 LibraryItem
- **THEN** 这些素材 SHALL 在该 FieldSession 分组下组织展示

#### Scenario: 分组能力不丢失
- **WHEN** 用户从比赛库浏览
- **THEN** FieldSession 分组 SHALL 仍可呈现「8 月 20 日北体训练采集」这类采集批次容器

## REMOVED Requirements

### Requirement: 按采集任务分组展示录制视频任务
**Reason**: FieldSession 资产分组从任务页迁移至比赛库，不再作为「分析任务」页「录制视频任务」Tab 内的一等分组能力
**Migration**: 分组能力在比赛库以 Collection/Folder（`match-library` / `library-item-projection`）呈现；任务页收敛为工程控制台