## 1. 封面预览能力模块

- [x] 1.1 新增 `src/components/library/` 下的封面预览模块：module 级 `Map<streamUrl, dataURL>` 缓存 + LRU 上限（约 200 条），提供「命中缓存渲染 `<img>` / 未命中用临时 `<video>` 解码约 0.05s 落缓存后换 `<img>`」的统一解码组件
- [x] 1.2 实现按来源分派的封面布局：单摄/上传单画面；双摄 `cam_1 | cam_2` 左右拼接、各半幅 `object-cover` 裁黑边 + 「双摄」角标；双摄某路缺失显中性占位

## 2. 数据侧双摄机位流

- [x] 2.1 `libraryAdapter.ts` 的 `LibraryItemViewModel` 类型新增 `cameraCoverSources?: { cam_1?: string; cam_2?: string }`
- [x] 2.2 `buildLibraryItems` 与 `resolveLibraryItemByRef` 的 `sync_recording` 分支用 `getVideoStreamUrl(registered_video_ids.cam_1/cam_2)` 填充 `cameraCoverSources`（缺失则省略），保留 `coverVideoUrl` 兼容

## 3. 接入 LibraryCard

- [x] 3.1 `LibraryCard.tsx` 封面区替换为封面预览能力组件，按 `item.cameraCoverSources`/`cameraSetup` 分派渲染

## 4. 导航衔接修复

- [x] 4.1 `router.ts`：`captureHome (/capture)` 的 `navigationSection` 由 `"videos"` 改为 `"capture"`；同步更新 `router.test.ts` 断言
- [x] 4.2 `LandingPage.tsx`：「进入开始使用」`onNavigate("/capture")` → `onNavigate("/library")`
- [x] 4.3 `NewAnalysisPage.tsx`：Landing shell 下主视觉区新增「返回比赛库」按钮 → `onNavigate("/library")`

## 5. 测试与回归

- [x] 5.1 新增封面预览能力渲染测试：单画面 / 双摄拼接 / 缓存命中断言 / LRU 有界
- [x] 5.2 新增 `libraryAdapter` 双摄 `cameraCoverSources` 投影单测（含机位流缺失省略）
- [x] 5.3 更新 `router.test.ts` 中 `/capture` 的 `navigationSection` 断言
- [x] 5.4 运行 `npm run test` 与 `npm run lint && npm run typecheck`，手动验证：比赛库返回封面即时显示、双摄左右拼接封面、上传页返回、首页入口进比赛库、现场采集侧边栏高亮