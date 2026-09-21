## 1. 播放器：拆分「自然播完」与「被中断」

- [x] 1.1 在 `src/components/SegmentVideoPlayer.tsx` 新增 `interruptionRef`，并在 `seekVideo`、`syncToTakeTime`、`stepForward`、`stepBackward` 进入前置位（这些路径都会改动 `currentTime` 而不代表自然播放到达）。
- [x] 1.2 确认键盘逐帧路径同样置位：`handleFrameStep` 与 `handleKeyDown` 中的方向键分支都会改 `currentTime`，需与 1.1 用同一个标记。
- [x] 1.3 扩展完成回调签名为携带原因（`"completed" | "interrupted"`）；`finishSegmentPlayback` 判定到达终点后按标记报告原因，报告后清除标记；`ended` 分支同样报告 `"completed"`。
- [x] 1.4 扩展 `SegmentVideoPlayerHandle` / props 中受影响的类型，确保 `tsc -b` 通过且三个调用点无需改动即可编译。

## 2. 页面：开关状态与补集推导

- [x] 2.1 在 `src/pages/SegmentManagerPage.tsx` 新增开关状态，初值**开启**；不写入 localStorage 或任何持久化。
- [x] 2.2 落实非比赛时间口径（**实施时修订**）：跳过由「续播目标 = 起点不早于当前窗口结束时间的第一个 algorithm 回合」**隐式实现**（见 4.3），不单独落地补集 memo —— 该集合在进度条配色（回合/非回合）与续播逻辑之外没有任何消费点，单独落地即成死代码；已在续播选取处写明口径注释。
- [x] 2.3 开关不可用的判定：`autoRallySegments` 为空时置为不可用，并提供原因文案（无正式切分结果 / 无自动回合）。
- [x] 2.4 复核模式（`reviewMode`）下不向播放器传任何开关数据，使控件不出现——用调用点意图表达，不依赖"复核模式下恰好没有回合数据"。

## 3. 播放器：开关控件按数据可选启用

- [x] 3.1 新增可选 props：开关当前值、变更回调、是否可用、不可用原因。四个都不传时**不渲染该控件**，DOM 与交互与引入前一致。
- [x] 3.2 在控制条内渲染开关控件，位置与播放/暂停、逐帧、静音、全屏同排；不可用时禁用并显示原因（`title` 或等效提示）。
- [x] 3.3 确认 `ScoringCalibrationWorkbenchPage.tsx:541` 与片段页第二个机位播放器不传这些 props，外观与行为不变。

## 4. 页面：续播编排

- [x] 4.1 在完成回调的处理里按原因分流：仅 `"completed"` 才进入续播判定；`"interrupted"` 维持现状（清窗口 + 暂停 + 置 idle）。
- [x] 4.2 续播判定：开关关闭 → 维持现状；开关开启且无下一个区间 → 停在终点暂停，不循环。
- [x] 4.3 选取续播目标：`autoRallySegments` 中「起点 ≥ 当前窗口结束时间」的第一个区间；**不得**按数组下标递推（需支持从人工片段出发）。
- [x] 4.4 抽取一条与 `handleSegmentClick` 共用的播放窗口 helper，续播与点击走同一条路径，保证 `playbackWindowRef`、`playbackMode`、`activeSegmentId` 三者一致更新。

## 5. 播放器：提示合并与最小静默间隔

- [x] 5.1 新增常量 `AUTO_RALLY_CUE_MIN_GAP_MS = 1000`（与既有 `AUTO_RALLY_CUE_VISIBLE_MS` 并列，可在人工确认后调整）。
- [x] 5.2 在 cue 数据上新增可选来源字段（用户主动 / 自动续播），省略时按「用户主动」处理（最保守：永远提示）。
- [x] 5.3 改造提示状态机：显示窗口**开启期间**的任何回合变化只就地更新序号，不重新淡入、不延长窗口。
- [x] 5.4 窗口**未开启**时：用户主动来源立即开窗；自动续播来源需距上次窗口结束 ≥ 最小静默间隔才开窗，否则抑制。
- [x] 5.5 记录上次窗口结束时刻，并在窗口关闭时更新它（供 5.4 判定）。

## 6. 测试

- [x] 6.1 `src/components/SegmentVideoPlayer.test.tsx`：分段播放后 `seekToTakeTime` 中断，断言回调原因为 `"interrupted"`。
- [x] 6.2 同文件：逐帧前进越过有效终点，断言回调原因为 `"interrupted"` 且不触发续播语义。
- [x] 6.3 同文件：自然播放到终点断言回调原因为 `"completed"`；既有「播放片段到终点后自动暂停并通知页面」用例保持通过（签名扩展向后兼容）。
- [x] 6.4 同文件：不传开关 props 时控件不存在；传入时可见；不可用时禁用并带原因。
- [x] 6.5 同文件：提示合并——连续切换回合 id 于显示窗口内，断言文字就地更新且期间只有一次淡入（用 `data-auto-rally-cue` 状态与 fake timers 断言）。
- [x] 6.6 同文件：最小静默间隔——自动续播来源在静默期内不开启新窗口；用户主动来源在同样时间点仍然开窗。
- [x] 6.7 `src/pages/SegmentManagerPage.test.tsx`：默认开启 + 多个自动回合，模拟当前区间播完，断言播放窗口推进到下一个回合起点、`playbackMode` 保持 `segment`、`activeSegmentId` 更新。
- [x] 6.8 同文件：开关关闭时同一场景断言仍为「暂停 + idle」。
- [x] 6.9 同文件：最后一个区间播完断言停在终点且不回到第一个区间。
- [x] 6.10 同文件：拖动进度条中断当前区间播放，断言**不**续播且播放头停在用户指定位置。
- [x] 6.11 同文件：人工片段播完后续播目标为「其后第一个自动回合」，验证 4.3 的选取规则。
- [x] 6.12 同文件：`autoRallySegments` 为空时开关不可用；`boundary-review` 模式下开关控件不出现且既有复核断言仍通过。

## 7. 验证与人工确认

- [x] 7.1 运行 `npm test`，确认新增用例与既有 `SegmentVideoPlayer.test.tsx`、`SegmentManagerPage.test.tsx` 全部通过；与改动前基线（691 tests / 690 passed / 1 failed，唯一失败为 `EditableSegmentTimeline.test.tsx:45` 既有问题）对比，确认未新增失败。
- [x] 7.2 运行 `npm run build`，确认 `tsc -b` 通过；对本变更触及的文件与 `HEAD` 版逐文件对比 lint 问题数，确认未新增。
- [x] 7.3 人工确认：默认开启下点击一个回合，播完自动跳到下一个回合并跳过中间内容；最后一个回合播完停下不循环。
- [x] 7.4 人工确认：拖动进度条不被弹走，可停在非比赛区间；手动拖入非比赛区后按播放不会自动跳走。
- [x] 7.5 人工确认：逐帧越过区间终点不触发跳转；关闭开关后行为完全回到「播到终点自动暂停」。
- [x] 7.6 人工确认：连续短回合素材上提示**只有一块**、序号就地跳数、无「刚淡出又淡入」的双闪；并据此调整 `AUTO_RALLY_CUE_MIN_GAP_MS`。
- [x] 7.7 人工确认：`?mode=boundary-review` 下开关不出现、复核流程不受影响；`ScoringCalibrationWorkbenchPage` 未出现该控件。

### 实施记录（2026-09-19）

改动文件（`git status --porcelain src/` 全量，相对上一轮新增/修改的只有前两个）：

| 文件 | 改动 |
| --- | --- |
| `src/components/SegmentVideoPlayer.tsx` | ①新增 `SegmentPlaybackEndReason` 与 `interruptionRef`，`onSegmentPlaybackEnd` 签名扩展为携带原因，`seekVideo`/`syncToTakeTime`/`stepForward`/`stepBackward`/`handleFrameStep`/方向键路径置位，`playSegment` 与 `onPlay` 清除；②`AutoRallyCue` 新增可选 `cause` 字段与常量 `AUTO_RALLY_CUE_MIN_GAP_MS`，提示状态机改为「显示窗口 + 来源标记 + 最小静默间隔」；③新增 `AutoSkipControl` prop 与控制条开关控件 |
| `src/pages/SegmentManagerPage.tsx` | 新增 `autoSkipEnabled`（默认开启，不持久化）与不可用原因；`activeAutoRally` 携带 `cause`；`handleSegmentPlaybackEnd` 按 reason 分流并实现续播；`playbackWindowRef` 在非复核点击分支补记；`handleSegmentClick`/`handleTimelineSeek`/`handleTimelineSegmentClick` 复位续播来源标记；主播放器传入 `autoSkip` |

未新增 `src/index.css` 样式：开关是文字按钮，用既有 Tailwind 类即可。

验证结果：

- `SegmentVideoPlayer.test.tsx` **28 passed**（原 19 + 新增 9）；`SegmentManagerPage.test.tsx` **29 passed**（原 29 + 新增 6，其中先前 29 条含自动回合提示用例）。全量 **706 tests / 705 passed / 1 failed**，唯一失败仍是 `EditableSegmentTimeline.test.tsx:45` 的既有基线问题，本次未新增失败。
- `npm run build`（`tsc -b && vite build`）通过，2589 modules transformed。
- lint：`SegmentManagerPage.tsx` 与 HEAD 版同为 **14 problems / 14 errors**（boundary-review 收敛遗留的死代码）；`SegmentVideoPlayer.tsx` **0 errors / 1 warning**（既有 `exhaustive-deps`）。未新增 lint 问题。

**实施中的三处修正（记录以防复现）**：

1. **任务 2.2 按实际落地方式修订**（见该条目内注）：补集集合在配色与续播逻辑之外没有消费点，单独落地即成死代码；口径由 4.3 的续播选取规则隐式实现。
2. **`useMemo` 内读 ref 被编译器 lint 拦截**（`Cannot access refs during render`）：续播来源标记从 ref 改为 state `autoAdvancePending`。时序上成立的原因——续播分支（完成回调）与下一次时间更新分属不同事件批次，state 必然先提交。
3. **提示合并的第一版实现有真 bug**：就地更新分支把既有定时器一并清掉，窗口因此**永不淡出**（测试「显示窗口内的多次回合变化只就地更新文字」当场暴露）。修正为：窗口内**保留原定时器**只换文字；仅在开新窗前清定时器。

**既有测试兼容性**：`onSegmentPlaybackEnd` 签名扩展为携带原因后，既有两条断言（`SegmentVideoPlayer.test.tsx`「播放片段到终点后自动暂停并通知页面」、`SegmentManagerPage.test.tsx` 复核相关）只检查调用次数、不检查参数，原样通过。
