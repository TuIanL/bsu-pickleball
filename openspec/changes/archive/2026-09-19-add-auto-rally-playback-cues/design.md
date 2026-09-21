## Context

正式自动回合切分已写入产品链路：`backend/app/services/formal_segmentation_service.py:94-113` 在切分成功后把每个回合发布为 `CaptureSegment`，`segment_type=rally`、`source=algorithm`、`edit_status=active`、`segmentation_run_id=<run>`，`ordinal` 与 `label`（`第X回合`）由发布方按时间顺序写定。前端 `SegmentManagerPage` 已经消费这套数据，但只在右侧「自动回合切分」区域逐条列出（`src/pages/SegmentManagerPage.tsx:186-193` 的 `modelSegments`），回放面上没有任何同步提示。

回放面的现状：

- 视频画面是一个 `<video>`（`src/components/SegmentVideoPlayer.tsx:221-227`），无任何叠加层，其外层容器也没有定位上下文。
- 下方进度条是原生 `<input type="range">`，靠 `accent-[#22C55E]` 上色（`src/components/SegmentVideoPlayer.tsx:229-240`）。它只能表达「已播放 / 未播放」，无法表达区间结构。
- 页面底部另有一块时间线 `EditableSegmentTimeline`，它已经按盘/局/分三轨着色（`src/components/EditableSegmentTimeline.tsx:19-23`）。**本变更不动它** —— 用户要改的是播放器下方那条进度条。

页面已经具备本变更需要的全部输入：`currentTimeMs`（`SegmentManagerPage.tsx:53`）、`durationMs`（`:54`）、`segments`、`segmentationSummary`。不需要任何后端或 API 改动。

约束：`SegmentVideoPlayer` 是共享组件，除 `SegmentManagerPage`（`:1039`、`:1060`）外还有 `ScoringCalibrationWorkbenchPage.tsx:541` 一个调用点，且被 `SegmentVideoPlayer.test.tsx` 直接单测。因此新增能力必须是**可选启用**：不传新数据时，组件的 DOM 结构与交互必须与改动前逐项一致。

## Goals / Non-Goals

**Goals:**

- 让用户在回放时立刻知道「现在播到第几回合」，不必回看列表比对时间戳。
- 让进度条一次性表达整段视频的切分结构：哪些区间是回合、哪些是回合间歇。
- 全部改动收敛在片段页回放面，且只消费已发布的正式切分结果，不引入新的数据来源或接口。
- 「其他功能与样式保持不变」可被审计：不传新数据的调用路径零行为差异。

**Non-Goals:**

- 不改后端、不改切分算法、不新增或修改任何 API 契约。
- 不改动 `EditableSegmentTimeline`（页面底部时间线）的现有三轨配色与拖拽行为。
- 不改动片段列表的排序、筛选、只读约束与播放/编辑入口。
- 不把人工片段或人工关键事件纳入叠加提示与进度条配色。
- 不在普通片段页引入置信度、阈值、复核或编辑入口。

## Decisions

### D1：中央提示的触发规则取「所属回合发生变化」而非「区间内常驻」

页面按 `currentTimeMs` 推导当前所属自动回合，播放器在**该回合 id 发生变化**时显示一次大字，约 2 秒后淡出；同一回合内不重复出现。

选择理由：用户原始诉求是「播放到某一回合时提示当前回合序号」。常驻会让大字长期压在画面中央、遮挡比赛内容；而「仅播放中显示」会导致暂停定格查看回合时反而看不到序号。按 id 变化触发一次，天然覆盖三种进入路径——连续播放跨过边界、拖动进度条跨过边界、点击列表某回合直接跳入区间——且不会重复打扰。

代价：用户在同一个回合内来回拖动不会再次看到提示。可接受，因为此时画面右侧的列表高亮仍在指示当前回合。

### D2：叠加层放在播放器组件内，由页面传入数据

`SegmentVideoPlayer` 新增两个可选 prop：当前自动回合（`{ id, ordinal } | null`）与自动回合区间数组。页面负责算数据，播放器只负责渲染与时序。

选择理由：

- 页面已经持有计算所需的一切（`currentTimeMs`、`segments`、`segmentationSummary`），且有现成的 `useMemo` 推导惯例（`modelSegments`、`playableSegments`、`timelineTotalMs`）。
- 时序（触发、计时、淡出）是纯展示逻辑，放进播放器可避免页面多出一组 timer 状态；播放器也是唯一知道叠加层该盖在哪个元素上的地方。
- 反过来让播放器自己去算「当前是第几回合」会把片段业务语义塞进一个通用播放器，并让 `ScoringCalibrationWorkbenchPage` 白白承担这份耦合。

**备选（未采纳）**：在页面里包一层绝对定位的 overlay div。播放器的根容器没有 `relative`，页面侧包一层就得靠外部约定对齐视频画面尺寸，视频 `aspect-video` 一变形就错位；而且第二个机位播放器（review 模式）会被漏掉。

### D3：当前回合的推导口径与页面现有的 `modelSegments` 必须分开

新建一个独立 memo，而不是复用 `modelSegments`，也不是复用 `playableSegments`：

- 不能复用 `modelSegments`（`SegmentManagerPage.tsx:186-193`）：它建立在 `filteredSegments` 之上，被列表筛选器 `filter` 过滤（默认值 `"rally"`，但用户可切到 `set`/`game`/`all`）。列表筛选是「我在找哪一类片段」，与「视频现在播到第几回合」无关；复用会让切筛选器时进度条配色凭空变化。
- 不能复用 `playableSegments`：它混入人工片段（过滤条件只有 `edit_status === "active"`），而且按**时长升序**排序（`:199-204`），用于 `find` 会优先命中短片段。

新口径：`edit_status === "active"` **且** `source === "algorithm"` **且** `segmentation_run_id === segmentationSummary.run_id`，按 `start_ms` 升序。同时要求 `source` 与 `segmentation_run_id` 双条件，是为了与 `formal-match-state-segmentation` 的发布契约逐字对齐，也避免把未来可能出现的其它带 run id 的来源算进来。

区间取 `effective_start_ms ?? start_ms` 与 `effective_end_ms ?? end_ms`，与页面其它位置（`findSegmentAtTime`、`timelineTotalMs`）一致。

### D4：区间判定用左闭右开，末端缺失视为延伸到媒体末尾

判定条件为 `currentTimeMs ∈ [start, end)`，步长取整毫秒。用左闭右开是因为首尾相接的两个回合在共享边界上必须只命中一个，`<=` 会让 `find` 命中先出现的那个，产生一个瞬时但可观测的错误编号。

`end_ms` 缺失（防御性分支，正式发布路径总会写入）时按 `durationMs` 处理，与 `findSegmentAtTime`（`SegmentManagerPage.tsx:208-214`）的现有约定一致。

### D5：进度条配色保留原生 `<input type="range">`，只接管它的轨道与滑块观感

三段式分层，自下而上：

1. 底层——分段色带：整条为「非回合」色，其上按区间叠加「自动回合」色块。仅在存在自动回合区间且 `duration > 0` 时渲染。
2. 中层——已播放遮罩：宽度为 `已播放时间 / duration` 的半透明白条，用来补回被接管后丢失的「已播放 / 未播放」读数。
3. 顶层——原生 `<input type="range">`，加一个作用域类（`.rally-band-progress`），用 `appearance: none` 关掉原生轨道渲染，只把滑块（`::-webkit-slider-thumb` / `::-moz-range-thumb`）画出来。

**备选一（未采纳）**：完全自绘进度条，把 range 用 `opacity: 0` 盖住。问题是滑块位置只能由 `currentTime` state 驱动，而 `handleProgressChange`（`SegmentVideoPlayer.tsx:213-217`）是命令式 seek、不更新 state，`currentTime` 只在 `timeupdate` 事件（约 4Hz）时刷新 —— 拖动时滑块会明显滞后于手指/指针。另外 range 被视觉隐藏后键盘焦点不可见，是无障碍回退。

**备选二（未采纳）**：把色带放在进度条正下方的独立细条。零回归风险，但配色不在进度条本体上，与需求「映射到播放进度条」的字面要求不符。

分层的前提是色带层与 range 的轨道严格同尺。range 的 `min=0`、`max=Math.max(duration, 1)`，色带按同一个 `duration` 归一化（`SegmentVideoPlayer.tsx:232`）。色带层用 `absolute inset-0` 与 range 同盒模型，且只有 range 一个在流内子元素，因此不需要额外的尺寸同步。

`appearance: none` **只在色带启用时**生效（条件类名），未启用时那条进度条仍是 `accent-[#22C55E]` 的原生渲染，与改动前逐像素一致。

配色沿用应用内既有语义：自动回合 `#22C55E`（与 `EditableSegmentTimeline` 的「分」轨同色）、非回合 `#334155`、已播放遮罩 `rgba(255,255,255,0.28)`、进度条底色 `#1a1a2e`（沿用 `SegmentVideoPlayer.tsx:228` 现有底色）。

### D6：无正式切分结果时不做任何着色

当 `segmentationSummary` 为空、`run_id` 为空，或自动回合集合为空时：不显示中央提示，进度条保持现有外观。

选择理由：`status = valid_no_rallies` 时把整条涂成「非回合」色，与「还没跑切分」在视觉上无法区分，会把「无数据」误读为「已识别且全场无回合」。保持现状是唯一不产生错误推断的处理。这一条同时让改动在缺少切分结果的老素材上完全不可见。

### D7：中央提示不进无障碍树，用 `data-` 属性承载测试断言

叠加层设 `aria-hidden="true"`：它是一个 2 秒即消失的视觉提示，内容与右侧列表高亮完全重复；若进无障碍树，屏幕阅读器会在播放过程中反复播报，反而掩盖真正的状态变化。测试断言改挂在 `data-auto-rally-cue="visible|hidden"` 属性上。

### D8：闪现时长取模块常量 2000ms，不做成 prop

2 秒足够读一个「第X回合」，又不至于压住画面。做成 prop 会让共享组件的接口多一个只有片段页用得上的参数；需要调整时改常量即可。淡出用 `transition-opacity duration-500` 配 `setTimeout`，组件卸载时清理计时器。

### D9：生效范围天然限定在普通片段页

`segmentationSummary` 在 `boundary-review` 隔离模式下被显式置为 `null`（`SegmentManagerPage.tsx:98-100` 的 review 分支），而叠加与色带都以 `run_id` 为前提，因此研发复核模式不会出现这两项能力，无需额外的模式判断。页面侧仍显式传 `undefined`，把「哪些模式启用」表达为调用点意图，而不是依赖隐式巧合。

## Risks / Trade-offs

- **`::-webkit-slider-thumb` / `::-moz-range-thumb` 覆盖后滑块可能在某些浏览器不可见** → 滑块是唯一被自绘的可交互部件，最坏情况是「能拖但看不见」。缓解：色带层加 `pointer-events-none`，已播放遮罩的右边缘本身构成一条可见的位置指示，即使滑块渲染失败也能读出播放位置；同时 `src/index.css` 里同时写 WebKit 与 Gecko 两套伪元素。若目标浏览器仍失败，回退到 D5 的备选二（独立细条）。
- **jsdom 下 `video.duration` 默认 `NaN`** → 若色带不设 `duration > 0` 前置条件，测试会因除零/`NaN` 宽度而假失败。缓解：把 `duration > 0` 作为渲染条件写进实现，测试用 `Object.defineProperty(video, "duration", ...)` + `fireEvent.loadedMetadata` 提供时长（该手法在 `SegmentVideoPlayer.test.tsx:40-42` 已有先例）。
- **`timeupdate` 约 4Hz，边界可能晚 250ms 才切换提示** → 大字闪现本身对百毫秒级延迟不敏感；且页面内只有这一个时间源，符合 `segment-playback-editing-sync` 既定的「统一片段回放状态」。不为此引入第二个时钟。
- **页面新增 memo 漏掉 `effective_*` 与 `edit_status` 口径** → 会与列表展示不一致。缓解：测试覆盖「切筛选器不改变色带区间」与「人工片段不触发提示」两条反向断言。
- **共享组件接口扩张** → 两个新 prop 均为可选，且 `ScoringCalibrationWorkbenchPage` 不传值；用一条「不传新 prop 时无叠加层、进度条不带作用域类」的单测把这条性质固定下来。

## Migration Plan

纯前端、无数据迁移、无接口变更。部署即生效；回滚只需还原三个前端文件（`SegmentManagerPage.tsx`、`SegmentVideoPlayer.tsx`、`index.css`），无产物或数据库残留。

验证顺序：`npm test`（新增单测 + 既有 `SegmentVideoPlayer.test.tsx`、`SegmentManagerPage.test.tsx` 全绿）→ `npm run build`（`tsc -b` 保证新 prop 类型在所有调用点合法）→ 人工在片段页确认三件事：跨回合播放时大字闪现一次、暂停后拖动进度条跨回合仍会闪现、切列表筛选器不改变进度条配色。

## Open Questions

- 非回合区间的 `#334155` 与进度条底色 `#1a1a2e` 明度接近，在低亮度显示器上可能区分度不足。若人工验证后认为需要加强，改为 `#475569` 或给非回合区段加一道浅色描边，均不改变本设计的数据口径。
- 中央大字的字号取了随宽度伸缩的区间值（约 28–64px）。实际投影/大屏场景下的最佳字号需人工在真实素材上确认。
