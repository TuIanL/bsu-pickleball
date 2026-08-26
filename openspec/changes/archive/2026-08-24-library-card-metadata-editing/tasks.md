## 1. 后端：FieldSession 日期可更新

- [x] 1.1 `FieldSessionUpdate`（schema）增加 `started_at: datetime | None = None` 字段，允许 PATCH 仅更新日期而不动其它字段
- [x] 1.2 核对 `PATCH /api/field-sessions/{id}`（routes_field_sessions.py）已能将 `started_at` 持久化到 FieldSession 模型；必要时扩展 `update_field_session` service
- [x] 1.3 确认 `live` / `recording` 状态场次更新 `started_at` 不被 `update_field_session` 的「进行中禁止修改」拦截（仅放开日期字段）

## 2. 后端：upload video 显示名/日期真源

- [x] 2.1 video registry / `VideoMetadata` 数据模型新增 `display_title`、`display_date` 字段（默认空，缺省回退 `original_filename` / `uploaded_at`）
- [x] 2.2 新增 `updateVideo(id)` service：写入 `display_title` / `display_date`，空值视为撤销覆盖
- [x] 2.3 新增 `PATCH /api/videos/{video_id}` 路由，请求体含 `display_title` / `display_date`，返回更新后的 `VideoMetadata`
- [x] 2.4 新增 `PATCH /api/recordings/{id}`、`PATCH /api/sync-recordings/{id}` 兜底路由与 service（请求体含 `display_title`/`display_date`），供无 `fieldSessionId` 的素材使用（方案 C 默认走 FieldSession）。**本期仅实现后端，不接 UI（见 design Q2 决议 B）**

## 3. 前端 adapter：displayTitle / displayDate

- [x] 3.1 `libraryAdapter.ts` 的 `LibraryItemViewModel` 增加 `displayTitle?: string` / `displayDate?: string`
- [x] 3.2 三处组装（sync_recording / recording / upload）中：`displayTitle` 取 FieldSession.title（有场次）或 video.display_title（upload）；`displayDate` 取 FieldSession.started_at（有场次）或 video.display_date（upload）
- [x] 3.3 `resolveLibraryItemByRef` 同步填充 `displayTitle` / `displayDate`
- [x] 3.4 `LibraryCard` 渲染：标题展示值 = `displayTitle ?? 既有 title`；日期展示值 = `displayDate ?? 既有 startedAt`（保持现有 `formatDate` 渲染）

## 4. 前端：analysisClient API 封装

- [x] 4.1 `updateFieldSession(id, { title?, started_at? })` 封装（复用既有 PATCH 端点）
- [x] 4.2 `updateVideo(id, { display_title?, display_date? })` 封装（新端点）
- [x] 4.3 （可选）`updateRecording` / `updateSyncRecording` 兜底封装

## 5. 前端：LibraryCard 重构与内联编辑

- [x] 5.1 将 `LibraryCard` 信息区（标题/日期/标签）移出导航 `<button>`，封面独立为导航 button（点封面进详情）
- [x] 5.2 新增 `InlineEditTitle` 子组件：标题 hover 显示浅铅笔图标 + 轻底色；点击进入受控 `<input>`，品牌色 ring 编辑态；Enter/Esc/失焦保存或取消；空值撤销
- [x] 5.3 新增 `InlineEditDate` 子组件：日期 hover 显示浅铅笔图标 + 轻底色；点击进入原生 `<input type="date">`（仅到日）；选择即保存
- [x] 5.4 编辑态视觉（品牌 ring + 浅底）与整卡导航 hover（`shadow-md`）明确区分；三态（导航/可编辑 hover/编辑中）视觉可分辨
- [x] 5.5 编辑区位于导航 button 之外，点击编辑绝不触发详情导航

## 6. 前端：LibraryPage 接入回调

- [x] 6.1 `LibraryPage` 新增 `handleUpdateTitle(item, value)` / `handleUpdateDate(item, value)`：按 `ref.kind` 路由——`upload` 调 `updateVideo`；`recording`/`sync_recording` 且有 `fieldSessionId` 调 `updateFieldSession`；**无 `fieldSessionId` 的 recording/sync 本期不暴露编辑（B 决议）**
- [x] 6.2 保存成功后调用 `reconcileItem(item.ref)` 定向局部刷新，不重建全库
- [x] 6.3 保存失败（网络/422）保留编辑态并轻量提示，不跳转
- [x] 6.4 将 `onUpdateTitle` / `onUpdateDate` 透传至 `LibraryGrid` → `LibraryCard` props
- [x] 6.5 确认自定义标题立即可被顶部搜索匹配（现有 `query` 已匹配 `title`）
- [x] 6.6 列表排序按展示日期（displayDate）倒序，不回退到 uploaded_at（Q1 决议）

## 7. 品牌改名：拍动视析 → 瞬境

- [x] 7.1 `index.html`：`<title>` 与 meta description 改为「瞬境」并同步平台描述
- [x] 7.2 `src/data/productCopy.ts`：`brand` 改为「瞬境」，tagline 去掉 TENG-IMU 硬件叙事
- [x] 7.3 `src/components/platform/AppSidebar.tsx`：侧边栏 logo 文字改为「瞬境」
- [x] 7.4 `src/components/platform/AppShell.tsx`：landing 顶部 logo 与 footer 文案改为「瞬境」

## 8. 验证与回归

- [x] 8.1 有场次素材：编辑标题/日期 → 同场次多张卡同步更新；搜索自定义名可命中（adapter 单测 + 手工验证路径确认）
- [x] 8.2 upload 素材：编辑标题/日期 → 持久化到 video；`uploaded_at` 不变；列表按展示日期（displayDate）倒序
- [x] 8.3 编辑态不误触导航；Enter/Esc/失焦行为正确；空标题撤销
- [x] 8.4 与进行中 `library-cover-poster` 错开 apply，确认 `LibraryCard.tsx` / `libraryAdapter.ts` 无冲突
- [x] 8.5 补充/更新单测：adapter `displayTitle`/`displayDate` 映射（三来源）、API 封装、卡片编辑交互（hover 提示 + 编辑态不导航）
