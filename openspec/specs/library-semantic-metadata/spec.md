# library-semantic-metadata Specification

## Purpose
把 Library 用户层从「数据库投影页」升级为语义化比赛库：标题解析策略、工程 ID 去暴露、卡片标签去重、真实封面接入、基于统一 displayState 的筛选，以及菜单 action 门控。

## Requirements
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

### Requirement: 工程 ID 去暴露

用户层（Library 卡片、Workspace 概览、标题栏）SHALL 隐藏 raw 工程标识（sourceId / fieldSessionId / captureTakeId），改用语义化展示。

#### Scenario: 概览不显示原始 ref
- **WHEN** Workspace 概览渲染资产标识
- **THEN** 系统 SHALL 展示语义化信息（如「7月20日训练 · 男双 · 1号场」）
- **AND** SHALL NOT 直接显示 `sync_recording:sync_...` 或场次 `fs_...` 原值

#### Scenario: 场次分组语义化
- **WHEN** Library 按场次分组展示
- **THEN** 分组标题 SHALL 使用 FieldSession 语义名称
- **AND** SHALL NOT 显示 `场次 fs_...` 原值

### Requirement: 卡片标签去重

Library 卡片属性标签 SHALL 消除语义重复（source 类型 / camera 设置 / 比赛形式不再同义并列展示）。

#### Scenario: 双摄双打只显示一组标签
- **WHEN** 一个双摄、双打素材渲染属性行
- **THEN** 系统 SHALL 展示去重后的标签集（如「双摄 · 双打」或「现场采集 · 双摄 · 双打」）
- **AND** SHALL NOT 出现「双摄 · 双摄 · 双打」的同义重复

### Requirement: 封面 conditional plumbing

Library 卡片 SHALL 读取 `thumbnailUrl` / `previewUrl`：存在稳定 URL 时渲染真实画面，不存在时展示中性占位，且 SHALL NOT 在前端伪造截图。真实 poster 字段与 hover preview 不属于本 Change 交付（另开 `add-library-media-previews`）。

#### Scenario: 有封面字段时显示真实画面
- **WHEN** 素材提供 thumbnail/preview（如 sync_recording 的 reference camera 首/中帧）
- **THEN** 卡片封面 SHALL 展示真实画面

#### Scenario: 无封面字段时保持占位
- **WHEN** 素材未提供 thumbnail/preview
- **THEN** 卡片 SHALL 展示中性占位封面，不伪造画面
- **AND** SHALL NOT 因封面缺失阻塞卡片的其余渲染

### Requirement: 卡片信息区可编辑优先

Library 卡片信息区（标题、日期）SHALL 由只读派生改为可编辑优先：用户通过卡片上的行内编辑覆盖展示值，覆盖值持久化后对所有读取路径（卡片、搜索、分组）生效。

#### Scenario: 编辑后搜索生效
- **WHEN** 用户重命名某素材标题
- **THEN** 列表搜索按该自定义名称 SHALL 可命中该素材
- **AND** 该素材的展示值 SHALL 立即反映新名称，不依赖刷新全库