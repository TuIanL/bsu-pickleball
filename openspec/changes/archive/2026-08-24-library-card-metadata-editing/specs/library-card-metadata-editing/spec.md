# library-card-metadata-editing Specification

## Purpose
比赛库卡片标题与日期的可视化内联编辑与持久化：hover 铅笔提示、行内编辑交互（标题文本输入、日期原生选择器仅到日）、方案 C 混合真源写入，以及编辑态与导航态的视觉区分。

## Requirements

### Requirement: 卡片标题行内编辑

比赛库卡片 SHALL 在标题右侧提供 hover 可发现的编辑入口（浅铅笔图标 + 轻高亮）；点击 SHALL 进入行内文本编辑，回车保存、Esc 取消、失焦保存。

#### Scenario: hover 显示编辑提示
- **WHEN** 用户将指针悬停在卡片标题上
- **THEN** 系统 SHALL 显示浅铅笔图标与文字轻底色，提示该标题可编辑
- **AND** 该高亮 SHALL 与整卡导航 hover（`shadow-md`）视觉不同

#### Scenario: 点击进入编辑并保存
- **WHEN** 用户点击标题
- **THEN** 系统 SHALL 将标题切换为受控 `<input>`，预填当前展示值，并加品牌色 ring 表示编辑态
- **AND** 用户按回车或使输入框失焦时 SHALL 保存该值
- **AND** 用户按 Esc SHALL 取消编辑并恢复原值

#### Scenario: 空标题不持久化
- **WHEN** 用户清空标题并保存
- **THEN** 系统 SHALL 撤销编辑、保留原展示值，不写入空串

#### Scenario: 编辑不触发导航
- **WHEN** 用户在编辑态点击标题输入框
- **THEN** 系统 SHALL NOT 导航到详情页（标题编辑区位于导航 button 之外）

### Requirement: 卡片日期行内编辑

比赛库卡片 SHALL 在日期行提供 hover 可发现的编辑入口；点击 SHALL 进入原生日期选择（仅到日，不含时间），保存后持久化。

#### Scenario: 点击进入日期编辑
- **WHEN** 用户点击日期行
- **THEN** 系统 SHALL 弹出原生 `<input type="date">` 选择器（仅日期，不含时/分）
- **AND** 选择后 SHALL 保存为新的展示日期

#### Scenario: 日期编辑视觉区分
- **WHEN** 日期处于可编辑 hover 或编辑态
- **THEN** 系统 SHALL 使用与标题一致的浅提示/品牌 ring 样式，与整卡导航 hover 视觉不同

### Requirement: 编辑态与导航态视觉区分

卡片信息区的可编辑元素 SHALL 拥有与整卡导航 hover 不同的视觉层级：导航 hover 为整卡轻微上浮（`shadow-md`），可编辑 hover 为浅铅笔+轻底，编辑中为品牌色 ring + 浅底。

#### Scenario: 三态视觉可区分
- **WHEN** 卡片处于「导航 hover」「可编辑 hover」「编辑中」三种状态之一
- **THEN** 用户 SHALL 能仅凭视觉区分当前处于哪种交互，不会把编辑误认为翻页

### Requirement: 方案 C 混合真源写入

标题/日期保存 SHALL 按素材类型写入正确的真源：有 `fieldSessionId` 的 recording / sync_recording 写入对应 FieldSession（标题改 `title`、日期改 `started_at`）；upload 写入 video 自身的 `display_title` / `display_date`。

#### Scenario: 有场次的素材改 FieldSession
- **WHEN** 用户编辑一个 `recording`/`sync_recording` 素材的标题或日期且该素材有 `fieldSessionId`
- **THEN** 系统 SHALL PATCH `/api/field-sessions/{id}` 写入 `title` / `started_at`
- **AND** 同 FieldSession 下的其他素材 SHALL 同步反映新标题/日期

#### Scenario: upload 素材改 video 自身
- **WHEN** 用户编辑一个 `upload` 素材的标题或日期
- **THEN** 系统 SHALL PATCH `/api/videos/{id}` 写入 `display_title` / `display_date`
- **AND** SHALL NOT 修改系统 `uploaded_at`（上传时间保留只读）

#### Scenario: 保存后局部刷新
- **WHEN** 标题/日期保存成功
- **THEN** 系统 SHALL 定向重投影该素材（局部刷新），不重建全库列表
- **AND** 自定义名称 SHALL 立即可被列表搜索匹配

### Requirement: 品牌命名统一为瞬境

Web 端 SHALL 将产品品牌名「拍动视析」统一为「瞬境」，覆盖页面标题、logo 文案与产品文案中的品牌字段。

#### Scenario: 浏览器标签与 meta
- **WHEN** 用户打开应用
- **THEN** `index.html` 的 `<title>` 与 meta description SHALL 使用「瞬境」

#### Scenario: 应用内 logo 与页脚
- **WHEN** 用户查看侧边栏 logo 或 landing 页顶部/页脚
- **THEN** 品牌文案 SHALL 显示「瞬境」，不再显示「拍动视析」
- **AND** `src/data/productCopy.ts` 的 `brand` 字段与 tagline SHALL 同步更新（去掉 TENG-IMU 硬件叙事）
