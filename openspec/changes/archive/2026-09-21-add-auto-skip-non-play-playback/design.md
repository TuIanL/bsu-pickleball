## Context

片段页的播放编排集中在 `SegmentManagerPage`：`handleSegmentClick`（`:613-630`）在非复核模式下调用 `playerRef.current?.playSegment(start, rawEnd)` 播一个窗口；`handleSegmentPlaybackEnd`（`:664-668` 附近）在窗口播完后 `pauseAllPlayers()` + `setPlaybackMode("idle")`；`playbackWindowRef` 记录当前窗口，`playbackMode` 是 `"idle" | "segment"` 两态。

窗口播完的通知来自播放器：`SegmentVideoPlayer` 的 `finishSegmentPlayback`（在 `timeupdate` 里判定 `currentTime >= endSeconds - 0.03`）会钳制时间、`pause()`、然后回调 `onSegmentPlaybackEnd`。

**本次要绕开的核心陷阱**：`onSegmentPlaybackEnd` 目前混用了两种语义。`seekVideo`（`SegmentVideoPlayer.tsx:58-69`）在 `segmentLoopRef.current !== null` 时也会清掉窗口并回调它；而片段页非复核模式拖动进度条/时间线走的正是这条路——`handleTimelineSeek`（`:651-666`）→ `seekAllPlayers` → `seekToTakeTime` → `seekVideo`。因此把「自动续播」直接挂在 `onSegmentPlaybackEnd` 上，**用户一拖进度条就会被弹到下一段**，直接违背「拖动仍可自由定位」这条需求。

同时，既有两条规格现在保证「播到有效终点自动暂停」：`segment-playback-editing-sync` 的 `### Requirement: 片段播放完成后自动暂停`（主规格 `:46-61`）与 `segment-manager` 的 `### Requirement: 片段管理页保持播放头和列表高亮同步` 内的「播放自动停止」场景（主规格 `:80-95`）。默认开启的开关是对它们的正面覆盖，必须同步改规格。

数据侧的前提已查实：前端能拿到的回合数据是 `autoRallySegments`（由已归档的 `auto-rally-playback-cues` 引入），取自当前已发布 run 的 active algorithm Rally，按 `startMs` 升序。模型的三分类状态 `("rally_active", "non_play", "unknown")` 只存在于切分 artifact 的 `state_timeline` 中，唯一读取入口是 job 级接口（`backend/app/api/routes_analysis.py:80`），而 take 级摘要未暴露 `planning_job_id`（`backend/app/api/routes_segment_editing.py:246-257`）——所以模型分类在本变更中不可用。

约束：`SegmentVideoPlayer` 有三个调用点（`SegmentManagerPage` 两处、`ScoringCalibrationWorkbenchPage.tsx:541`），新能力必须按数据可选启用。

## Goals / Non-Goals

**Goals:**

- 连续观看多个回合时不再需要逐分手动拖动跳过中间空白。
- 跳转行为完全可预期：什么时候会跳、什么时候不会跳，都有明确规则且被规格固定。
- 不牺牲使用者对播放位置的控制权——弱约束下用户拖到哪里就停在哪里。
- 不引入后端改动，不改变进度条配色与回合提示的数据口径。

**Non-Goals:**

- 不区分「真正的非比赛（暂停/换边）」与「分间准备」——补集口径刻意把两者一并跳过。
- 不新增后端接口，不使用模型 `non_play` / `unknown` 分类。
- 不做「强约束」（把落在非比赛区间的播放头强制弹回）。
- 不为进度条增加第三个颜色。
- 不改动 `EditableSegmentTimeline`、片段列表、自动回合回放提示的触发条件与停留时长。
- 不改动 `ScoringCalibrationWorkbenchPage` 的行为。

## Decisions

### D1：「非比赛时间」＝ algorithm 回合的补集

在 `[0, 媒体总时长)` 上取 `autoRallySegments` 的差集，得到「将被跳过」的区间集合。**刻意不区分**这些缺口的成因，因此该集合同时包含：

- 分间发球准备（人工事件里 `intermission_kind="between_rallies"` 的那一类，**属于比赛时间**）；
- 暂停与换边（`intermission_kind` 为 `timeout` / `side_change`）；
- 模型判为 `unknown` 的低证据区段；
- 时长不足 500ms、被解码器压制掉的漏检回合（`backend/app/vision/match_state/decoder.py:96-99` 会把它们改写成 `non_play`）。

用户的明确选择就是"只看击球段落、其余硬切"，所以前三类一并跳过是符合意图的。第四类是**知情的代价**：模型漏检的真实比赛内容会被跳过，而且跳过去之后使用者无法察觉。之所以接受，是因为要抑制它就必须区分 `non_play` 与 `unknown`，而那需要新增 take 级后端接口，超出本变更范围。

**未采纳**：复用已在时间线上的 `non_play_start` / `non_play_end` 事件（`MiniTimeline.tsx:44-64` 有现成配对逻辑）。原因是 `useLiveCoding.ts:337/348/359/421` 显示实时比赛编码**每结束一分就写一条 `non_play_start(between_rallies)`**，即该事件类型下绝大多数区间是发球准备时间；按它跳过会把每一分之间都跳掉，与「跳过非比赛内容」的直觉相反。要正确使用它必须先按 `intermission_kind` 过滤，而那会把「分间准备」留下来——与 D1 的目标相反。

### D2：开关在组件层是「按数据可选启用」，在片段页是「默认开启」

这两件事不矛盾，但容易混淆，实现时必须分开表达：

- **组件层**：`SegmentVideoPlayer` 新增可选的开关 prop（值 + 变更回调 + 是否可用 + 不可用原因）。不传的调用方**不渲染该控件**，行为与引入前完全一致——这是 `ScoringCalibrationWorkbenchPage` 不受影响的唯一依据。
- **页面层**：`SegmentManagerPage` 持有该状态并**初始化为开启**。

「默认开启」指的是片段页的初值，不是组件的行为。

### D3：把 `onSegmentPlaybackEnd` 拆成「自然播完」与「被中断」两种语义

回调签名扩展为携带原因（`"completed" | "interrupted"`），播放器内部通过一个 `interruptionRef` 标记判定：

- 在 `seekVideo`、`syncToTakeTime`、`stepForward`、`stepBackward` 以及键盘逐帧路径**进入前**置位；
- `finishSegmentPlayback` 判定到达终点时，若标记已置位则报告 `"interrupted"`，否则报告 `"completed"`；
- 报告后清除标记。

**只有 `"completed"` 才允许触发续播。** 这是弱约束的必要实现条件——不是额外防护，而是「拖动仍可自由定位」这条需求能成立的唯一方式。逐帧越过段尾也会被正确归入 `"interrupted"`，因为逐帧改的是 `currentTime`、必然经过上述置位点。

**未采纳**：新增一个独立的 `onSegmentPlaybackComplete` 回调、保留 `onSegmentPlaybackEnd` 原样。理由是调用点只有一处语义分支，加第二个回调会让调用方必须同时处理两个"看起来一样"的回调，更容易接错；带 `reason` 的单回调把区分点放在类型上。

### D4：续播编排留在页面，播放器只报告事实

播放器不感知「回合」概念，只报告「这个窗口被完整播完了」。页面在收到 `"completed"` 时决定要不要续播。判断顺序：

1. 开关未开启 → 维持现状（`pauseAllPlayers()` + `setPlaybackMode("idle")`）。
2. 开关开启但**不存在**下一个区间 → 停在当前终点并暂停，不循环。
3. 否则 → 调用与 `handleSegmentClick` 同一条播放路径播放下一个区间，并保持 `playbackMode = "segment"`、更新 `activeSegmentId`。

「下一个区间」的判定用 `startMs >= 当前窗口结束时间` 的**第一个** `autoRallySegments` 条目，而不是「当前回合的数组下标 + 1」。理由：用户也可能点击一个**人工片段**（`handleSegmentClick` 接受任意 `CaptureSegmentSummary`），从人工片段的终点往后找第一个自动回合才是自洽的语义，按下标推进在人工片段上无定义。

**未采纳**：把续播逻辑写进播放器。播放器是通用组件，塞入回合语义会让 `ScoringCalibrationWorkbenchPage` 无端承担这份耦合。

### D5：开关控件放在播放器控制条，不持久化，复核模式强制禁用

- **位置**：控制条内，与播放/暂停、逐帧、静音、全屏同排。它是播放行为，放在播放控制旁边最直观。
- **不持久化**：用户在同批选择中未选「记住上次」，因此每次进入片段页都回到默认开启；用户关闭只对当前会话有效。这是刻意的，避免多一个跨素材共享的持久化状态要维护。
- **复核模式**：`?mode=boundary-review` 下页面**不传**开关数据（等同于"该控件不存在"），保证复核能停在边界看前后帧。用调用点意图表达，而不是依赖"复核模式下恰好没有回合数据"这类隐式巧合。
- **不可用状态**：无正式切分结果（无 `run_id` 或无 algorithm 回合）时，控件禁用并给出原因文案，而不是静默生效。

### D6：提示合并用一个「显示窗口 + 来源标记 + 最小静默间隔」状态机

播放器侧的提示逻辑从「id 变化就重新闪现」扩展为：

- **显示窗口开启期间**发生的任何回合变化 → **只就地更新文字**为最新序号，不重新淡入、不延长窗口（窗口到点仍淡出）。
- **窗口未开启**时发生回合变化：
  - 变化由**用户主动操作**引起 → **立即开启新窗口**（不受任何节流），保证既有规格「暂停与定位同样触发」不被违反；
  - 变化由**自动续播**引起 → 距上次窗口结束不足最小静默间隔时**不开窗**，否则正常开窗。

来源通过 cue 数据上的可选字段表达（省略时按「用户主动」处理，即最保守的"永远提示"）。页面在续播路径上把它标为自动来源；播放器据此决定是否节流。

**为什么必须有最小静默间隔**：只做"窗口内合并不重启"还不够。若窗口在 t=2.0s 淡出、而自动续播在 t=2.2s 又引起一次变化，就会出现"刚淡出 0.2 秒又淡入"的双闪——正是需求要消除的现象。静默间隔把两次**独立的**淡入强制拉开。窗口内则是连续可见的一块，不计入双闪。

### D7：不对 `auto-rally-playback-cues` 提 `MODIFIED`

该规格的 `### Requirement: 播放头进入自动回合时的中央叠加提示` 有六个 Scenario，逐一核对后无一被本变更违反：

- 「跨入新回合时提示一次」要求显示「第X回合」——合并不重启淡入时，块仍在画面正中央显示着正确序号，满足；且合并只会让显示**更少**，不会重复。
- 「自动淡出」要求约 2 秒后淡出——窗口时长不变，满足。
- 「暂停与定位同样触发」由 D6 的用户来源分支显式保证不受节流影响。
- 「离开全部自动回合」「不遮挡播放器交互」「提示文字保持可读」均不受影响。

因此本变更只**细化**自动续播这一子情形下的呈现方式，不修改该能力的触发条件与时长。为避免日后读者误判为遗漏，这条结论以 HTML 注释写在 proposal 的 `Modified Capabilities` 处，并在本 design 中留证。

## Risks / Trade-offs

- **`onSegmentPlaybackEnd` 语义拆分会影响既有测试** → `SegmentVideoPlayer.test.tsx` 的「播放片段到终点后自动暂停并通知页面」与 `SegmentManagerPage.test.tsx` 的「复核队列中选择回合从有效起点播放，并在有效终点自动暂停」都断言该回调被调用，但**不检查参数**，因此签名扩展向后兼容、可原样通过。风险在于新的 `"interrupted"` 分支可能没有覆盖到——缓解：为「拖动中断」与「逐帧越过段尾」各补一条断言，显式锁定它们不触发续播。
- **默认开启是破坏性变更** → 所有既有使用者在升级后立刻遇到"点一个回合播完会自动往下走"。缓解：开关就在控制条上、一键可关；且规格已把两条既有 requirement 改成条件式，避免"规格说暂停、实际在续播"的文档漂移。若日后判断默认开启过激，把它翻成默认关闭是单点改动。
- **被跳过的内容不可见** → 补集口径会跳过模型漏检的真实比赛内容，使用者不会知道错过了什么。缓解：进度条上的非回合配色恰好标出了这些区间（由已归档的 `auto-rally-playback-cues` 提供），使用者至少能看到"这里有一大段被跳过"。这是本次不使用第三色的直接后果，也是它可接受的原因。
- **弱约束产生一个语义空洞** → 跳转的唯一触发点是「片段自然播完」，所以手动把播放头拖进非比赛区间后按播放**不会**自动跳走。这不是缺陷，但极易被误读为漏实现。缓解：写成显式 Scenario，并在交付说明里点明。
- **连续跳转时"下一段"可能极短** → 若相邻两个 algorithm 回合几乎相接，续播会立刻又触发一次完成判定。缓解：正式发布的最短回合时长受 500ms 压制规则约束，且 `finishSegmentPlayback` 有 0.03 秒容差；测试里用最短合法时长构造一条断言覆盖。
- **复核模式的判定时机** → 开关的启用与否取决于 URL 上的 `mode` 查询参数，而该参数在页面初始化时读取。缓解：与既有 `reviewMode` 用同一个来源，不引入第二套判定。

## Migration Plan

纯前端，无数据迁移、无接口变更。部署即生效；回滚只需还原 `src/components/SegmentVideoPlayer.tsx` 与 `src/pages/SegmentManagerPage.tsx`，规格侧回滚 `openspec/specs/` 下两份被改的规格。

验证顺序：`npm test`（新增用例 + 既有两个测试文件全绿）→ `npm run build` → 人工确认六项：默认开启下点击回合会连续播到下一段、最后一段停下不循环、拖动进度条不被弹走、手动拖入非比赛区后播放不自动跳、逐帧越过段尾不跳、复核模式下开关不出现。

## Open Questions

- 最小静默间隔取 1000ms 是估值，用于保证「淡出 500ms + 静默」不会与下一次淡入重叠。真实观感需要人工在连续短回合素材上确认，可能需要调整。
- 开关控件在控制条上的具体呈现（文字标签还是图标加提示）未定，按人工视觉验收结果调整，不影响任何数据口径与交互规则。
