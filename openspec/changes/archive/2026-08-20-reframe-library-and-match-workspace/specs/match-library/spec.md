## ADDED Requirements

### Requirement: 比赛库页面作为用户主入口

系统 SHALL 提供 `/library` 作为统一资产入口，以缩略图卡片展示所有 upload / recording / sync_recording 素材，并支持搜索、过滤、排序与分组。

#### Scenario: 展示素材卡片
- **WHEN** 用户访问 `/library`
- **THEN** 系统按卡片呈现素材，卡片显示画面预览、标题、时间、机位与比赛形式、生命周期状态

#### Scenario: 搜索与过滤
- **WHEN** 用户在比赛库输入关键词或选择过滤条件（全部 / 正在分析 / 已完成 / 失败 / 上传 / 录制 / 双摄）
- **THEN** 系统 SHALL 只显示匹配的素材

#### Scenario: 高质量缩略图预览
- **WHEN** 素材分析完成且存在缩略图
- **THEN** 卡片 SHALL 使用更清晰的画面预览，桌面端 hover 时可播放循环片段；无预览时显示占位且不伪造

### Requirement: FieldSession 作为采集来源的 Collection / Folder 分组

系统 SHALL 将 FieldSession 作为 Library 的一级组织方式（Collection / Folder），而不是 LibraryItem 本身；FieldSession 的录制分组能力从任务页迁入 Library。

#### Scenario: FieldSession 展示为文件夹
- **WHEN** 存在一个 FieldSession「8 月 20 日北体训练采集」
- **THEN** 该 FieldSession SHALL 作为一组素材的容器展示，其下包含若干 LibraryItem

#### Scenario: capture_mode 语义保护
- **WHEN** 素材的 capture_mode 为 `engineering`
- **THEN** 该素材 SHALL 默认不混入普通 `match` / `practice` 主列表
- **AND** 通过「筛选 → 显示工程素材」或工程模式可查看

### Requirement: 素材生命周期显示与最近比赛

系统 SHALL 在比赛库主视图展示生命周期状态，并提供「最近比赛」等排序视图。

#### Scenario: 显示最近比赛
- **WHEN** 用户查看比赛库默认视图
- **THEN** 系统 SHALL 按时间倒序展示最近比赛，并允许排序（时间 / 名称等）

#### Scenario: 卡片状态标注
- **WHEN** 素材处于某种生命周期状态
- **THEN** 卡片 SHALL 明确标注「比赛 / 训练 / 待分析 / 正在分析 / 分析完成 / 分析失败」中的对应文案，且副标题声明「统一管理比赛、训练与采集视频及其分析结果」