## MODIFIED Requirements

### Requirement: 语义化标题解析

LibraryItem 的展示标题 SHALL 按优先级解析为语义化命名，且用户可编辑的覆盖值具有最高优先级；`court_name` 仅作为次要 metadata，不得再作为用户可见主标题。

#### Scenario: 用户可编辑覆盖值最高优先
- **WHEN** 素材存在用户编辑过的 `displayTitle`（或对应真源的 `title` / `display_title`）
- **THEN** 展示标题 SHALL 采用该用户覆盖值
- **AND** SHALL NOT 回退到 matchTitle / FieldSession 标题 / 时间+形式 / source id

#### Scenario: 有分析 metadata 优先用比赛标题
- **WHEN** 素材无用户覆盖值，且关联的 analysis metadata 提供 `matchTitle`
- **THEN** 展示标题 SHALL 采用该 match title
- **AND** 其次回退到 FieldSession 标题，再回退到「时间 + 比赛形式」，最后才用 raw source id

#### Scenario: 标题与 courtName 去重
- **WHEN** 卡片同时展示标题与场地名称
- **THEN** 同一值不得在两处重复出现

#### Scenario: 日期解析同样支持用户覆盖
- **WHEN** 素材存在用户编辑过的 `displayDate`（或对应真源的 `started_at` / `display_date`）
- **THEN** 卡片日期 SHALL 采用该用户覆盖值
- **AND** 缺失时回退到录制开始时间 / 上传时间派生值

### Requirement: 卡片标签去重

Library 卡片属性标签 SHALL 消除语义重复（source 类型 / camera 设置 / 比赛形式不再同义并列展示）。

#### Scenario: 双摄双打只显示一组标签
- **WHEN** 一个双摄、双打素材渲染属性行
- **THEN** 系统 SHALL 展示去重后的标签集（如「双摄 · 双打」或「现场采集 · 双摄 · 双打」）
- **AND** SHALL NOT 出现「双摄 · 双摄 · 双打」的同义重复

## ADDED Requirements

### Requirement: 卡片信息区可编辑优先

Library 卡片信息区（标题、日期）SHALL 由只读派生改为可编辑优先：用户通过卡片上的行内编辑覆盖展示值，覆盖值持久化后对所有读取路径（卡片、搜索、分组）生效。

#### Scenario: 编辑后搜索生效
- **WHEN** 用户重命名某素材标题
- **THEN** 列表搜索按该自定义名称 SHALL 可命中该素材
- **AND** 该素材的展示值 SHALL 立即反映新名称，不依赖刷新全库
