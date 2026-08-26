## Context

比赛库（`LibraryPage` + `LibraryCard`）当前把**标题**与**日期**作为只读派生值：
- 标题（`LibraryCard.tsx:195`）：来自 `LibraryItemViewModel.title`，其真源在 `libraryAdapter.ts` 的 `semanticTitle()` —— 依次回退 matchTitle → FieldSession.title → 「时间+比赛形式」→ source id；upload 则直接取 `original_filename` 去扩展名。
- 日期（`LibraryCard.tsx:196-199`）：来自 `startedAt`（recording/sync 的 `started_at` 或 upload 的 `uploaded_at`），由卡片内 `formatDate()` 渲染为「今天/昨天/X月X日」。

整张卡当前是一个 `<button>`（`LibraryCard.tsx:128-216`），包裹封面+信息区，点击进详情页；标题/日期是不可交互文本。

用户希望在卡片上就近重命名标题、修改比赛日期（仅到日），以便用自定义名称搜索。同时产品对外品牌已从「拍动视析」统一为「瞬境」，Web 端 4 处文案需改名。

本设计在「不引入嵌套交互元素」「尊重现有数据模型」「与进行中的 `library-cover-poster` 不冲突」三条约束下，给出实现方案。

## Goals / Non-Goals

**Goals:**
- 卡片标题/日期可 hover 显示铅笔提示与高亮，点击进入行内编辑并持久化。
- 标题编辑：文本输入，回车保存、Esc 取消；日期编辑：原生 `date` 选择器（仅到日）。
- 编辑态视觉（品牌色 ring + 浅底）与整卡导航 hover（`shadow-md`）明显区分。
- 方案 C 混合真源：有 `fieldSessionId` 改 FieldSession；upload 改 video 自身 `display_title`/`display_date`。
- 品牌改名：拍动视析 → 瞬境（4 处）。

**Non-Goals:**
- 不引入第三方日期/弹层库；日期用原生 `<input type="date">`。
- 不修改封面渲染区域（`:134-190`），与 `library-cover-poster` 边界清晰。
- 不做卡片批量改名、不做标题/日期的历史版本或审计。
- 不做时间级精度（时/分）编辑。
- 不改搜索逻辑（已按 `title` 匹配，持久化后自动生效）。

## Decisions

### D1：重构信息区结构，避免嵌套交互元素
**决策**：把 `LibraryCard` 拆为「封面导航 button」+「信息区兄弟节点」两层。
- 封面（缩略图 + 角标 + 状态遮罩）保留为单一 `<button>`，点击进详情（`onNavigate(detailPath)`）。
- 标题、日期、标签移出该 button，作为同级 `<div>`。标题/日期各自为可点击/可聚焦的编辑控件。

**理由**：HTML 禁止交互元素（input/button）嵌套在 `<button>` 内。当前结构若直接把 input 塞进导航 button，focus 与点击行为会错乱。拆分为兄弟节点后，点标题/日期只触发编辑，绝不会误触导航。

**替代方案**：在导航 button 之上叠一层绝对定位的编辑浮层并 `stopPropagation()`。否决——浮层定位与键盘可达性更复杂，且仍共用一个语义混乱的容器。

### D2：编辑态视觉与导航态区分
**决策**：
- 整卡导航 hover：保持 `hover:shadow-md`（封面区域轻微上浮）。
- 标题/日期非编辑 hover：出现浅铅笔图标 + 文字轻底色（如 `hover:bg-[brand-soft]/60`），提示「可编辑」。
- 编辑中：input/date 控件加 `ring-2 ring-[var(--capture-brand-primary,#23985b)]` + 浅底边框，明确「编辑模式」，视觉权重高于行内 hover。

**理由**：用户明确要求「编辑高亮与整卡 button 不一致」。三态分层（导航 / 可编辑提示 / 编辑中）让用户在任意时刻清楚自己处于哪种交互。

### D3：方案 C 混合真源写入
**决策**：`LibraryPage` 持有两个回调：
- `onUpdateTitle(item, value)` / `onUpdateDate(item, value)`：
  - 若 `item.ref.kind === "upload"` → `PATCH /api/videos/{id}` 写 `{ display_title, display_date }`。
  - 否则（`recording` / `sync_recording`）且有 `fieldSessionId` → `PATCH /api/field-sessions/{fsId}` 写 `{ title, started_at }`；无 `fieldSessionId` 时降级写 recording/sync 的兜底接口（见 D5）。

**理由**：尊重当前数据模型——upload 是孤立素材（无 FieldSession），recording/sync 语义上属于「一场比赛（FieldSession）」，改同场次标题/日期应全场次一致。避免给 recording/sync 造一个与 FieldSession 平行的显示名称真源造成语义重复。

**替代方案**：A（只改 FieldSession，upload 不可编辑）/ B（每素材独立显示名）。A 排除了 upload；B 需 3 套新字段且与 FieldSession 语义冲突。C 折中最贴合现状。

### D4：adapter 优先取 displayTitle/displayDate
**决策**：`LibraryItemViewModel` 新增 `displayTitle?: string` / `displayDate?: string`。`buildLibraryItems` 与 `resolveLibraryItemByRef` 三处组装时：
- 有 `fieldSessionId`：取 `FieldSession.title` 与 `FieldSession.started_at` 作为 `displayTitle`/`displayDate`（已存在，沿用）。
- upload：取 video 的 `display_title` / `display_date`（新增字段），缺省为空。
- 卡片渲染：`title` 展示值 = `displayTitle ?? 既有 semanticTitle`；`startedAt` 展示值 = `displayDate ?? 既有 startedAt`。

**理由**：保持「派生只读」为默认、用户覆盖为最高优先的清晰优先级，与 `library-semantic-metadata` 既有解析链一致。

### D5：后端新增/扩展 PATCH 接口
**决策**：
- `FieldSessionUpdate`（schema）增加 `started_at: datetime | None = None`；`PATCH /api/field-sessions/{id}` 已存在，自动支持改日期。
- 新增 `PATCH /api/videos/{id}`：请求体含 `display_title`、`display_date`；service 持久化到 video registry（需新增字段 `display_title`/`display_date`，缺省回退 `original_filename`/`uploaded_at`）。
- `PATCH /api/recordings/{id}`、`PATCH /api/sync-recordings/{id}`：仅作兜底保留（方案 C 默认走 FieldSession），请求体含 `display_title`/`display_date`，避免无场次素材完全不可编辑。

**理由**：upload 缺少 FieldSession 真源，必须有自己的可写字段；recording/sync 默认走 FieldSession，兜底接口防止极端无场次情况。

### D6：保存后局部刷新
**决策**：`LibraryPage` 保存成功后调用 `reconcileItem(item.ref)`（已存在，定向重投影单素材）刷新该项，避免全库重建闪烁。保存失败（网络/422）保留编辑态并轻量提示（如卡片角标 toast 或 inline error），不跳转。

**理由**：`reconcileItem` 已用于分析 terminal 后的定向刷新，复用即可，影响面最小。

## Risks / Trade-offs

- **[Risk] 同场次多素材共享标题/日期** → 改一次 FieldSession.title 会让同场次所有卡标题同步变化，用户可能误以为只改了一张。→ **Mitigation**：UI 上标题区 hover 提示文案为「重命名本场」，日期同理；若需「仅改单张」，未来再引入 per-item override（本期不做）。
- **[Risk] upload 改 `display_date` 误覆盖 `uploaded_at`** → **Mitigation**：后端 `display_date` 为独立字段，`uploaded_at` 作为系统上传时间保留只读，列表排序仍按 `startedAt` 展示值但可考虑改为按 `uploaded_at` 稳定排序（见 Open Questions）。
- **[Risk] 与 `library-cover-poster` 同改 `LibraryCard.tsx` / `libraryAdapter.ts` 冲突** → **Mitigation**：两 change 改不同区域（封面 vs 信息区）与不同 adapter 字段（thumbnailUrl vs displayTitle）；apply 时错开顺序即可，冲突概率极低。
- **[Risk] 编辑态键盘可达性** → **Mitigation**：input 可聚焦，`Enter` 保存 / `Esc` 取消，失焦等同于取消或保存（取保存，需二次确认？本期取「失焦即保存」与点击铅笔一致）。
- **[Risk] 空标题** → **Mitigation**：保存时空标题回退为不写（撤销编辑），不持久化空串。

## Migration Plan

- 纯增量：新增字段 `display_title`/`display_date` 带默认空，旧视频 registry 无该字段时 adapter 回退既有值，无需数据迁移脚本。
- FieldSession.started_at 已存在，schema 仅扩展可写性，不影响既有读路径。
- 前后端可独立部署：后端先加接口、前端先读（字段缺失回退），灰度零停机。
- 回滚：前端回退到旧卡片即可恢复只读；后端接口删除不影响既有字段。

## Open Questions

- ~~列表默认排序目前按 `startedAt` 倒序（`LibraryPage.tsx:170`）。当 upload 被用户改了 `display_date`（比赛日）后，是否仍应按 `uploaded_at`（上传时间）排序以保持稳定？~~ **已决议：按展示日期（displayDate）排序**，即用户修改后的比赛日立即参与倒序，不回退到 uploaded_at。task 8.2 的「列表排序符合预期」以此为准。
- ~~recording/sync 无 `fieldSessionId` 的兜底编辑 UI 是否本期接入？~~ **已决议：选 B**——后端兜底接口（`PATCH /api/recordings/{id}`、`PATCH /api/sync-recordings/{id}`）照常实现，但本期卡片 UI 仅覆盖「有 fieldSessionId」的主路径；无场次录制卡暂不可编辑。未来若需支持，仅需给 `handleUpdateTitle/Date` 加 `else` 分支调兜底接口，后端零改动。
