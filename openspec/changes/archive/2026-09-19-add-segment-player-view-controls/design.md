## Context

片段页的播放器组件 `src/components/SegmentVideoPlayer.tsx` 目前只有六个能力：逐帧前进/后退、播放/暂停、原生进度条、时间读数、同步降级提示、机位选择下拉，以及 `←`/`→`（含 `Shift` 秒级跳转）与 `Space` 三组键盘快捷键（`handleKeyDown`，注册在带 `tabIndex={0}` 的根节点上）。

同仓的 `src/components/platform/VideoAnalysisCard.tsx` 早已实现全屏与静音，可直接照搬的既有约定有四条：

- 能力探测：`const fullscreenSupported = typeof document !== "undefined" && Boolean(document.fullscreenEnabled)`（`:592`）
- 状态同步：`fullscreenchange` 监听 + `document.fullscreenElement === containerRef.current`，不靠 state 猜（`:597-602`）
- 切换：`await document.exitFullscreen()` / `await container.requestFullscreen()`（`:805-813`）
- 尺寸变体：容器 `data-fullscreen={isFullscreen}` + `data-[fullscreen=true]:aspect-auto data-[fullscreen=true]:h-screen data-[fullscreen=true]:w-screen`，`<video>` 用 `absolute inset-0 h-full w-full object-contain`（`:852-858`）

两者的差异在于控制条的布局范式：`VideoAnalysisCard` 的控制条是**浮层**（`absolute inset-x-4 bottom-4` 叠在画面上，`:1218`），而 `SegmentVideoPlayer` 的进度条与控制条是**流内行**（视频下方两行，`bg-[#1a1a2e]`）。这决定了全屏时不能照抄它的容器结构。

约束：`SegmentVideoPlayer` 有三个调用点（`SegmentManagerPage.tsx:1039` 与 `:1099`、`ScoringCalibrationWorkbenchPage.tsx:541`），全部共用同一实现；`SegmentManagerPage` 在双摄复核模式下并排渲染两个实例，并靠页面级 `synchronizedPlaying` / `playbackWindowRef` 与 `playSegment` / `syncToTakeTime` 维持多视角同步。

本次改动的前置事实：`<video>` 外层已经有一个 `relative` 容器（由已归档的 `auto-rally-playback-cues` 引入，用于承载中央回合提示叠加层），但视频自身仍是 `className="w-full aspect-video bg-black"` 靠自身撑出高度。

## Goals / Non-Goals

**Goals:**

- 让片段页能把画面放大到整屏，从而看清固定机位视频里的远端球员。
- 补齐全屏与静音这两项，使片段页播放器不再明显弱于同仓的分析播放卡。
- 全屏后仍能拖进度、逐帧、切机位、切静音，即全屏不能以失去控制面为代价。
- 双摄并排场景下全屏一路不破坏既有多视角同步。

**Non-Goals:**

- 不做画面裁切放大（`object-fit: cover`）、不做滚轮缩放与拖拽平移。
- 不做倍速播放、画中画、单帧截图导出。
- 不改动 `VideoAnalysisCard`。
- 不改动 `EditableSegmentTimeline`、片段列表、自动回合回放提示的数据口径与触发规则。
- 不新增后端、API 或数据字段。

## Decisions

### D1：全屏对象取「视频画面 + 进度条 + 控制条」这一整块，新建内层容器承载

在全屏切换点（根节点）与视频之间插入一个内层容器，把 `ref` 与 `data-fullscreen` 放在它上面，它包住三行：视频区、进度条行、控制条行。全屏时用 `data-[fullscreen=true]:flex data-[fullscreen=true]:flex-col data-[fullscreen=true]:h-screen data-[fullscreen=true]:w-screen`，视频区取 `flex-1 min-h-0`。

**为什么不直接全屏根节点**：根节点带 `rounded-2xl border overflow-hidden bg-[var(--capture-surface-video)]`，整屏显示会在屏幕四周画出一圈边框和圆角；要覆盖就得把 `rounded-none` / `border-0` 等反向变体全挂在根节点上，把本特性与根的当前样式耦死。内层容器本来就是干净的，不需要任何覆盖。

**为什么不全屏 `<video>` 本身**：那会走浏览器原生视频全屏，控制面换成浏览器原生控件，应用自己的进度条、自动回合区间配色与中央回合提示全部消失。用户要的「放大看清动作」必须与「能控制」同时成立。

**为什么不照抄 `VideoAnalysisCard` 的浮层控制条**：那需要把现有的流内两行重做成绝对定位浮层，改变非全屏状态下的外观——超出本变更范围。用 flex 纵向排列即可让现有三行在全屏下自然分布。

### D2：`<video>` 改为绝对定位填充容器

视频容器 `relative aspect-video`，`<video>` 改为 `absolute inset-0 h-full w-full object-contain`。这同时满足三件事：非全屏下与原 `w-full aspect-video` 视觉等价；全屏下容器切到 `aspect-auto h-screen w-screen` 后视频填满并留边居中；`object-contain` 就是不裁切的实现，直接对应「按原始比例完整呈现」这条需求。这与 `VideoAnalysisCard:853-858` 的写法逐字一致。

### D3：全屏状态以 `document.fullscreenElement` 为唯一真源

用 `fullscreenchange` 事件驱动控件状态，判定条件是 `document.fullscreenElement === containerRef.current`。不额外维护「我要不要全屏」的意图 state，因为 Esc、浏览器控件、其它元素抢先全屏都会让意图与事实分叉。`fullscreenEnabled` 为假时控件 `disabled`。`requestFullscreen()` / `exitFullscreen()` 的 Promise 拒绝要捕获，否则浏览器拒绝时会留下未处理的 rejection；捕获后什么都不做——真实的成败由 `fullscreenchange` 给出。

**未采纳**：给 `requestFullscreen` 加 `webkit` 前缀分支以支持旧 Safari。既有实现没做，且现代 Safari 已支持无前缀 API；引入前缀会多一条无法在本环境验证的分支。若日后确有旧 Safari 需求再加。

### D4：静音以 `<video>.muted` 为真源，state 只做镜像

`volumechange` 监听把元素状态同步到渲染用 state；切换时先改元素再读回元素（`video.muted = !video.muted`）。与 `VideoAnalysisCard:726,742-745,801-802` 一致。不把 state 当真源，避免出现「图标显示已静音但元素仍在出声」这类分叉。默认不静音，保持与引入前一致的出声行为。

### D5：快捷键并入既有 `handleKeyDown`，字母键大小写不敏感，且只在焦点不在可输入控件内才响应

`F` / `M` 直接加进既有的关键帧处理函数，判定用 `e.key.toLowerCase()`。新增守卫：当 `e.target` 是 `input` / `select` / `textarea` 或被 `isContentEditable` 时为真时，字母快捷键直接返回。开发这个守卫的直接原因是控制条里有**机位选择 `<select>`**——下拉聚焦时按 `M` 会与浏览器的选项首字母跳转打架。

守卫**只加在新增的字母键上**，不动既有的 `←`/`→`/`Space`。既有 `Space` 的 `preventDefault` 行为保持不变，以免回退 `segment-playback-editing-sync` 里已固化的快捷键场景。

### D6：双摄并排下只全屏被点击的一路，靠 DOM 树不变保证同步与快捷键继续生效

全屏元素在渲染上进入顶层，但它在 DOM 树里仍是根节点的子节点，因此：

- 焦点在播放器内 → `keydown` 仍冒泡到根节点的 `onKeyDown`，全屏内快捷键可用；
- 控制条上的按钮仍调用页面传入的 `onPlaybackToggle` / `onSeekRequest` / `onFrameStepRequest`，即全屏内的操作照旧走页面级同步控制器，作用于两路；
- 另一路未被卸载，`timeupdate` 继续推进，因此退出全屏时两路的时间基准本来就是一致的。

这条是「全屏不破坏多视角同步」的全部依据，也是唯一需要人工确认「退出后两路仍对齐」的原因。

## Risks / Trade-offs

- **jsdom 不实现 Fullscreen API** → `document.fullscreenEnabled` 为 `undefined`、`requestFullscreen` 不存在，真跑 `requestFullscreen` 会抛错。缓解：测试分两类——一类只断言「不支持时控件禁用且其余能力可用」（无需 stub，可真实运行）；另一类 stub 掉 `fullscreenEnabled`、`requestFullscreen`、`exitFullscreen` 与 `fullscreenElement` 并手动派发 `fullscreenchange`，验证状态同步与尺寸变体。绝不为了测试方便在生产代码里放宽 `fullscreenEnabled` 守卫。
- **iOS Safari 上全屏可能形同虚设** → `SegmentVideoPlayer` 的 `<video>` **没有** `playsInline`，iOS 上视频一播放就会接管到系统原生全屏，自定义控件与我们新加的全屏按钮都用不上。这是引入本变更**之前就存在**的问题，且改动 `playsInline` 会改变 iOS 上「非全屏」的表现，超出本变更范围。缓解：不在本变更内处理，但必须在交付说明里点名，避免把「全屏做好了」误解为「iOS 上也能用」。
- **全屏下中央回合提示字号相对更小** → 提示字号是 `clamp(28px, 6vw, 64px)`（`.auto-rally-cue`），容器变宽后取到 64px 上限，相对整屏画面占比下降。功能上不影响可读性，缓解：记为 Open Question，需要时按 `data-[fullscreen=true]:` 变体单独调字号，不改变数据口径。
- **全屏元素与页面级键盘/滚动行为** → 全屏时页面背景仍在。缓解：全屏元素自带 `h-screen w-screen` 与不透明底色，视觉上完全覆盖；不额外做滚动锁定，避免与 `LibraryItemWorkspace` 的外层布局打架。
- **`object-contain` 是显式重述，不是行为变化（已核实）** → 三个引擎的 UA 样式表都把 `<video>` 的默认 `object-fit` 设为 `contain`：Blink `third_party/blink/renderer/core/html/resources/html.css`（`video { object-fit: contain; }`）、Gecko `layout/style/res/html.css:745-747`、WebKit `Source/WebCore/css/html.css:154-155`。因此显式写 `object-contain` 对非 16:9 素材不会改变既有表现（本来就会留边、不会拉伸），它只是把这条隐含依赖显式化，避免日后有人加全局 reset 时静默改变视频填充方式。**本 design 初稿把这条写成「行为变化」是错的，已更正。**

## Migration Plan

纯前端、无数据迁移、无接口变更。部署即生效；回滚只需还原 `src/components/SegmentVideoPlayer.tsx`（以及 `src/index.css`，若最终新增了全屏作用域样式）。

验证顺序：`npm test`（新增用例 + 既有 `SegmentVideoPlayer.test.tsx`、`SegmentManagerPage.test.tsx` 全绿）→ `npm run build` → 人工确认六项：窗口内进入/退出全屏、Esc 退出后控件状态正确、全屏内能拖进度与逐帧、全屏内画面按原比例留边不裁切、`F`/`M` 快捷键生效且下拉聚焦时不误触发、双摄模式下全屏一路后另一路仍同步且退出后对齐。

## Open Questions

- 全屏下是否要单独放大中央回合提示的字号（当前取 `clamp` 上限 64px）。不改变数据口径，属纯视觉调参，等人工在全屏下看过再定。
- 是否需要 `webkit` 前缀以支持旧版 Safari。既有实现未做，暂不引入。
- iOS Safari 缺 `playsInline` 导致的原生全屏接管是否要单独开一个变更处理。
