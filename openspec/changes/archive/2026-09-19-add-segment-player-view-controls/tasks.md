## 1. 视频容器结构

- [x] 1.1 在 `src/components/SegmentVideoPlayer.tsx` 内新增内层容器（承载全屏 `ref` 与 `data-fullscreen`），包住视频区、进度条行与控制条行三块，保持根节点现有的圆角/边框/底色不动。
- [x] 1.2 视频容器加上 `aspect-video`，`<video>` 由 `w-full aspect-video bg-black` 改为 `absolute inset-0 h-full w-full bg-black object-contain`，补 `playsInline` **不做**（见 design Risks，超出范围）。
- [x] 1.3 内层容器加全屏尺寸变体：`data-[fullscreen=true]:flex data-[fullscreen=true]:flex-col data-[fullscreen=true]:h-screen data-[fullscreen=true]:w-screen`；视频区在全屏下取 `flex-1 min-h-0`，使进度条与控制条固定在全屏底部。
- [x] 1.4 确认非全屏下容器高度仍由 `aspect-video` 决定、进度条与控制条仍按原顺序紧贴视频下方。

## 2. 全屏状态与控件

- [x] 2.1 新增 `containerRef` 与 `isFullscreen` state，以及 `fullscreenSupported` 能力探测（`typeof document !== "undefined" && Boolean(document.fullscreenEnabled)`）。
- [x] 2.2 注册 `fullscreenchange` 监听，用 `document.fullscreenElement === containerRef.current` 回写 `isFullscreen`，并在卸载时移除监听。
- [x] 2.3 实现 `toggleFullscreen`：已全屏则 `document.exitFullscreen()`，否则 `containerRef.current.requestFullscreen()`；捕获 Promise 拒绝且不吞掉其它错误，失败时不改状态（以 `fullscreenchange` 为准）。
- [x] 2.4 控制条新增全屏控件：`Maximize2` / `Minimize2` 图标、`aria-label` 随状态在「全屏播放」与「退出全屏」之间切换、`title` 同步、`disabled={!fullscreenSupported}`、`type="button"`。

## 3. 静音状态与控件

- [x] 3.1 新增 `isMuted` state，挂载时从 `<video>.muted` 读取初值。
- [x] 3.2 注册 `volumechange` 监听同步 `isMuted`，卸载时移除。
- [x] 3.3 实现 `toggleMuted`：翻转 `video.muted` 后从元素读回状态（元素为唯一真源）。
- [x] 3.4 控制条新增静音控件：`Volume2` / `VolumeX` 图标、`aria-label` 在「静音视频」与「打开声音」之间切换、`type="button"`，位置紧邻播放/暂停。
- [x] 3.5 确认切换静音不改变播放状态、播放位置与选中片段，且不触发任何请求。

## 4. 键盘快捷键

- [x] 4.1 在既有 `handleKeyDown` 中新增 `F`（切换全屏）与 `M`（切换静音），用 `e.key.toLowerCase()` 判定，与既有 `←`/`→`/`Space` 并列且互不干扰。
- [x] 4.2 新增可输入控件守卫：当 `e.target` 为 `input` / `select` / `textarea` 或 `isContentEditable` 为真时，字母快捷键直接返回且不 `preventDefault`（避免与机位选择下拉的首字母跳转冲突）。
- [x] 4.3 确认守卫只作用于新增字母键，既有的 `←`/`→`/`Space` 行为与 `preventDefault` 语义不变。

## 5. 测试

- [x] 5.1 `src/components/SegmentVideoPlayer.test.tsx`：不支持全屏的环境下全屏控件存在且 `disabled`，其余控件（播放/暂停、逐帧、进度条）仍可用。
- [x] 5.2 同文件：stub `document.fullscreenEnabled`、`Element.prototype.requestFullscreen`、`document.exitFullscreen` 与 `document.fullscreenElement`，点击全屏控件后断言调用了 `requestFullscreen` 且内层容器带 `data-fullscreen="true"`。
- [x] 5.3 同文件：在 `fullscreenElement` 指向容器时派发 `fullscreenchange`，断言控件切到「退出全屏」；再将其置空派发事件，断言状态回退（覆盖 Esc 退出路径）。
- [x] 5.4 同文件：`requestFullscreen` 返回 rejected Promise 时不抛未处理异常、`isFullscreen` 保持 false。
- [x] 5.5 同文件：点击静音控件后 `video.muted` 翻转且 `aria-label` 同步；派发 `volumechange` 后状态跟随元素。
- [x] 5.6 同文件：焦点在播放器内按 `F` / `M` 触发对应切换；焦点位于机位选择下拉时按 `M` 不改变静音状态。覆盖 `f`/`F` 大小写。
- [x] 5.7 同文件：回归——`Space`、`←`、`→` 与 `Shift+←/→` 的既有断言仍通过。
- [x] 5.8 `src/pages/SegmentManagerPage.test.tsx`：双摄复核模式下渲染两个播放器，断言各自独立持有全屏容器与控件（不共享状态）。

## 6. 验证与人工确认

- [x] 6.1 运行 `npm test`，确认新增用例与既有 `SegmentVideoPlayer.test.tsx`、`SegmentManagerPage.test.tsx` 全部通过；与改动前的基线失败口径对比，确认未新增失败。
- [x] 6.2 运行 `npm run build`，确认 `tsc -b` 通过。
- [x] 6.3 在真实素材上人工确认：窗口内进入/退出全屏；Esc 退出后控件状态正确；全屏内能拖进度条、逐帧、切机位。
- [x] 6.4 在真实素材上人工确认：全屏下画面按原始比例居中留边、不裁切不拉伸；中央回合提示与进度条回合配色随画面上屏。
- [x] 6.5 在真实素材上人工确认：`F` / `M` 快捷键生效；机位下拉聚焦时按 `M` 不误触发；`Space` / `←` / `→` 行为与改动前一致。
- [x] 6.6 双摄复核模式下人工确认：全屏一路后另一路继续同步播放，退出全屏后两路仍对齐；`ScoringCalibrationWorkbenchPage` 未出现非全屏外观变化。
- [x] 6.7 核实非 16:9 素材在非全屏下是否发生填充变化 —— 已核实为**非行为变化**：Blink / Gecko / WebKit 的 UA 样式表默认即 `video { object-fit: contain; }`（出处见 design Risks），显式声明等价于原状，无需人工确认。本项初稿把它写成「需确认的行为变化」是错的，已更正。

### 实施记录（2026-09-19）

改动文件（`git status --porcelain src/`）：

| 文件 | 改动 |
| --- | --- |
| `src/components/SegmentVideoPlayer.tsx` | 新增 `containerRef` / `isFullscreen` / `isMuted` 与 `fullscreenchange`、`volumechange` 监听；`toggleFullscreen` / `toggleMuted`；`isTextEntryTarget` 守卫；`handleKeyDown` 增加 `F`/`M`；渲染层新增全屏容器、视频改 `absolute inset-0 object-contain`、控制条新增静音与全屏两个控件 |
| `src/components/SegmentVideoPlayer.test.tsx` | 新增 8 条用例（不支持时禁用、申请全屏与状态切换、Esc 回退、请求被拒、全屏对象范围与画面口径、静音元素真源与回同步、F/M 大小写、可输入控件守卫） |
| `src/pages/SegmentManagerPage.test.tsx` | 新增 1 条用例（双摄复核下两个播放器各自独立持有全屏容器与控件） |

未新增 `src/index.css` 样式：全屏元素是新增的内层容器，本身没有圆角/边框，不需要反向覆盖。

验证结果：

- `SegmentVideoPlayer.test.tsx` 19 passed（原 11 + 新增 8）；`SegmentManagerPage.test.tsx` 23 passed（原 22 + 新增 1）。
- 全量：**691 tests / 690 passed / 1 failed**，唯一失败项与改动前同一处（`EditableSegmentTimeline.test.tsx:45` 的既有基线失败，属测试未同步、非产品缺陷），本次未新增失败。
- `npm run build`（`tsc -b && vite build`）通过，2589 modules transformed。
- lint 对比：`SegmentVideoPlayer.tsx` 改动前后均为同一条既有 `react-hooks/exhaustive-deps` warning（`getLiveCurrentTimeMs`），**0 error**。实施过程中一度引入 1 条 `@typescript-eslint/no-this-alias`（测试里用 `vi.fn(function(){ this })` 捕获全屏元素），已改为「把 `requestFullscreen` stub 只挂在待断言的那个元素上」——既消除了 lint 问题，又让「全屏对象是容器而非 `<video>`」本身成为被断言的属性。

**一条被自己推翻的断言（记录以防复现）**：design 初稿在 Risks 里写「原 `w-full aspect-video` 写法对非 16:9 素材会拉伸变形，本变更是行为修正」。查证后不成立——三个引擎的 UA 样式表默认就是 `video { object-fit: contain; }`，显式声明等价于原状。**教训：关于浏览器默认行为的事实，去引擎源码里查，不要凭印象写进 spec/design。**
