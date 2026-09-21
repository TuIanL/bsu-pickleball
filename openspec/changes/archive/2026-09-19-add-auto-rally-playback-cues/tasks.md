## 1. 页面层数据口径

- [x] 1.1 在 `src/pages/SegmentManagerPage.tsx` 新增「当前已发布 run 的 active algorithm Rally」memo：过滤条件为 `edit_status === "active" && source === "algorithm" && segmentation_run_id === segmentationSummary?.run_id`，按 `start_ms` 升序；`run_id` 为空时返回空数组。**不得复用** `modelSegments`（受列表筛选器影响）或 `playableSegments`（混入人工片段且按时长升序）。
- [x] 1.2 在该 memo 内同时导出播放器需要的两种视图：`{ id, ordinal }` 列表（用于中央提示判定）与 `{ id, startMs, endMs }` 区间数组（用于进度条配色）；起点取 `effective_start_ms ?? start_ms`，终点取 `effective_end_ms ?? end_ms`（`null` 时保持 `null`，由消费方按媒体总时长兜底）。
- [x] 1.3 新增「播放头当前所属自动回合」memo：以 `currentTimeMs` 在升序区间上取左闭右开 `[起点, 终点)` 命中项，终点为 `null` 时视为 `durationMs`；未命中返回 `null`。
- [x] 1.4 为该 memo 补一条 `durationMs` 变化的重算依赖，确保媒体元数据加载完成前后判定结果一致。

## 2. 播放器中央叠加提示

- [x] 2.1 在 `src/components/SegmentVideoPlayer.tsx` 的 props 中新增可选 `autoRallyCue?: { id: string; ordinal: number } | null`；`<video>` 外层包一个 `relative` 容器承载定位，保持 `aspect-video` 由 video 自身决定，不引入额外尺寸类。
- [x] 2.2 新增模块常量 `AUTO_RALLY_CUE_VISIBLE_MS = 2000`，以及「cue id 变化 → 显示 → 定时淡出」的 state + effect：`id` 与上次相同则不重复触发；`id` 变为 `null` 时立即隐藏并重置记录，使再次进入同一回合仍会提示一次。
- [x] 2.3 渲染叠加层：`absolute inset-0 grid place-items-center pointer-events-none`，文字为 `第{ordinal}回合`（与后端 `label` 同格式，不加空格），`opacity-90`、随宽度伸缩的字号、`-webkit-text-stroke` 深色描边并配 `paintOrder: "stroke"`、补一层低强度 `textShadow`；`opacity-0`/`opacity-90` 配 `transition-opacity duration-500` 实现淡入淡出。
- [x] 2.4 给叠加层加 `aria-hidden="true"` 与 `data-auto-rally-cue="visible"|"hidden"`；组件卸载时 `clearTimeout`，避免定时器泄漏。
- [x] 2.5 确认叠加层不覆盖播放器根节点上的 `onKeyDown`：逐帧、播放/暂停快捷键与既有按钮行为在提示可见时仍可用。

## 3. 进度条区间配色

- [x] 3.1 在 props 中新增可选 `autoRallyBands?: { id: string; startMs: number; endMs: number }[]`；未传入或数组为空时，进度条渲染路径与改动前完全一致（保留 `accent-[#22C55E]`）。
- [x] 3.2 把进度条包进 `relative` 容器，新增色带层 `pointer-events-none absolute inset-0 overflow-hidden rounded-full`：底层铺「非回合」色，其上按区间叠加「自动回合」色块，左偏移与宽度按 `时间 / duration` 归一化。仅当 `duration > 0` 且区间数组非空时渲染。
- [x] 3.3 色带层内叠加「已播放」遮罩：宽度 `currentTime / duration`，`rgba(255,255,255,0.28)`，用来补回被接管后丢失的已播放/未播放读数。
- [x] 3.4 对区间做裁剪与退化保护：起点钳到 `>= 0`、终点钳到 `<= duration`，裁剪后 `end <= start` 的区间直接丢弃。
- [x] 3.5 在 `src/index.css` 新增作用域类 `.rally-band-progress`：`appearance: none` + 透明轨道 + 自绘滑块（同时写 `::-webkit-slider-thumb` 与 `::-moz-range-thumb`，滑块 12px 圆形、`#22C55E` 填充配 `#1a1a2e` 描边、WebKit 侧 `margin-top: -3px` 居中）。
- [x] 3.6 仅在色带启用时给 `<input type="range">` 附加该作用域类；`min`/`max`/`step`/`disabled`/`onChange`/`aria-label` 保持原样，确保拖动定位行为与键盘可用性不变。

## 4. 接线与启用范围

- [x] 4.1 在 `SegmentManagerPage` 的主播放器调用点（`:1039` 附近）传入 `autoRallyCue` 与 `autoRallyBands`；`reviewMode` 为真时两者显式传 `undefined`，把启用范围表达为调用点意图。
- [x] 4.2 确认第二个机位播放器（`:1060` 附近）与 `ScoringCalibrationWorkbenchPage.tsx:541` 均不传新 prop，行为与改动前一致。

## 5. 测试

- [x] 5.1 `src/components/SegmentVideoPlayer.test.tsx`：不传新 prop 时无 `[data-auto-rally-cue]` 节点、进度条不带 `.rally-band-progress`，锁定「可选启用」契约。
- [x] 5.2 同文件：传入 `autoRallyCue` 后出现「第X回合」文本且 `data-auto-rally-cue="visible"`；用 `vi.useFakeTimers()` 推进 2000ms 后变为 `"hidden"`；同一 `id` 不变时不重复触发。
- [x] 5.3 同文件：传入 `autoRallyBands` 并通过 `Object.defineProperty(video, "duration", ...)` + `fireEvent.loadedMetadata` 提供时长，断言色带层存在、区间色块的 `left`/`width` 百分比正确、已播放遮罩宽度随 `timeupdate` 变化。
- [x] 5.4 同文件：`duration` 为 0 或区间数组为空时色带层不渲染，进度条仍为原生 `accent` 外观。
- [x] 5.5 `src/pages/SegmentManagerPage.test.tsx`：在已有 `seg_run_1` fixture 基础上补第二个自动回合，设置 `video.currentTime` 后 `fireEvent.timeUpdate`，断言进入不同区间时显示的序号随之变化；把播放头移到人工片段区间时不出现叠加层。
- [x] 5.6 同文件：切换片段列表筛选器（`rally` → `all`/`set`）后，断言色带区间数量与起止位置不变。
- [x] 5.7 同文件：`segmentationSummary` 为 `unavailable`/`run_id` 为空时，断言无叠加层且进度条不带 `.rally-band-progress`。
- [x] 5.8 同文件：`boundary-review` 模式下断言无叠加层与色带，且既有复核断言（`active-boundary-review`、确认并下一条）仍通过。
- [x] 5.9 同文件：断言整个过程中 `mocks.patchSegment`、`mocks.reviewSegmentBoundary`、`mocks.createAnalysisBatch` 均未被调用，锁定只读回放约束。

## 6. 验证与人工确认


- [x] 6.1 运行 `npm test`，确认新增用例与既有 `SegmentVideoPlayer.test.tsx`、`SegmentManagerPage.test.tsx` 全部通过。
- [x] 6.2 运行 `npm run build`，确认 `tsc -b` 下所有播放器调用点的新 prop 类型合法、无未使用变量告警。
- [x] 6.3 在真实素材上人工确认三项：跨回合连续播放时大字闪现一次并自动淡出、暂停后拖动进度条跨回合仍会闪现、切换列表筛选器不改变进度条配色。
- [x] 6.4 在真实素材上人工确认可读性与配色区分度：中央大字在明亮画面上清晰可读；「非回合」色与进度条底色在高亮度与低亮度显示器上均可区分（不满足时按 design 的 Open Questions 调整色值）。
- [x] 6.5 在 `ScoringCalibrationWorkbenchPage` 与片段页第二个机位播放器上确认外观与交互无变化。

### 实施记录（2026-09-19）

改动文件（`git status --porcelain src/` 全量）：

| 文件 | 改动 |
| --- | --- |
| `src/pages/SegmentManagerPage.tsx` | 新增 `autoRallySegments` / `activeAutoRally` 两个 memo；主播放器传入 `autoRallyCue` 与 `autoRallyBands`（`reviewMode` 时显式不传） |
| `src/components/SegmentVideoPlayer.tsx` | 新增可选 prop `autoRallyCue` / `autoRallyBands`、导出类型与常量 `AUTO_RALLY_CUE_VISIBLE_MS`；`<video>` 外层加定位上下文与中央叠加层；进度条加色带层 + 已播放遮罩 |
| `src/index.css` | 新增 `.auto-rally-cue` / `.auto-rally-cue--visible` 与 `.rally-band-progress`（含 WebKit / Gecko 两套滑块伪元素） |
| `src/components/SegmentVideoPlayer.test.tsx` | 新增 6 条用例（可选启用契约、闪现与淡出、指针穿透、时长映射、越界裁剪与退化丢弃、时长为零不启用） |
| `src/pages/SegmentManagerPage.test.tsx` | 新增 4 条用例（跨回合提示序号变化、人工片段不触发、筛选器不改变配色、无切分结果不启用、复核模式不启用） |

验证结果：

- `SegmentVideoPlayer.test.tsx` 11 passed（原 5 + 新增 6）；`SegmentManagerPage.test.tsx` 22 passed（原 18 + 新增 4）。
- `npm run build`（`tsc -b && vite build`）通过，2589 modules transformed。
- lint 对比：改动前后 `SegmentVideoPlayer.tsx` 均为 1 条既有 `react-hooks/exhaustive-deps` warning，`SegmentManagerPage.tsx` 均为 14 条既有 `@typescript-eslint/no-unused-vars` error（boundary-review 收敛后遗留的死代码）。本次改动未新增任何 lint 问题。

**已知基线失败（非本变更引入，未修复）**：全量 `npx vitest run` 为 682 tests / 1 failed。失败项为 `src/components/EditableSegmentTimeline.test.tsx:45` 「拖拽移动只更新本地预览，释放时只提交一次并携带 edit_version」。根因：该用例渲染 `EditableSegmentTimeline` 时未传 `reviewMode`，而拖拽把手只在 `reviewMode && !isSuperseded && !isArchived && !isOpen` 时渲染（`EditableSegmentTimeline.tsx:216-227`），`handlePointerDown` 也以 `if (!reviewMode) return;` 提前返回，于是 `container.querySelector(".cursor-col-resize")` 为 null，`fireEvent.pointerDown(null)` 抛错。判定依据：`git show HEAD:` 取出的 `EditableSegmentTimeline.tsx` 与 `EditableSegmentTimeline.test.tsx` 与工作区**逐字节相同**，且该测试文件只 import `./EditableSegmentTimeline` 与 `types/report`，均不在本次改动内，单文件运行同样失败。属「边界拖拽收敛进 `reviewMode` 后测试未同步」的历史遗留，按本变更范围不予修复。
