## Why

双摄同步录制的合并源视频（`{camera}_merged.mp4`）被以**分片封装**（`-movflags +frag_keyframe+empty_moov+default_base_moof`）写入（[sync_recorder_service.py](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/backend/app/camera/sync_recorder_service.py#L2362-L2363)），其 `moov` 只有 init、无完整 sample table，媒体样本分布在成百上千个 `moof`/`mdat` 分片里。浏览器原生 `<video src>` 对分片 MP4 不可靠播放，导致比赛库「数据分析/视频」视图弹出「视频加载失败（浏览器无法解码或网络中断）」，而 P1·启动回填等人形框因为来自 JSON overlay 仍会在黑底上渲染，观感割裂。

单摄录制（`+faststart` 非分片）一直正常；双摄合并视频在 commit `b20530d` 统一分片录制后被改为分片封装，从此双摄素材在浏览器播不了。

## What Changes

- **后端-合并产出浏览器可播源视频**：在双摄录制合并/最终化阶段，让合并源视频成为浏览器可播的 faststart 非分片 MP4。采取「先按现有分片写入 merge，再 `-c copy +faststart` 重新封装出一份播放版」或「合并直接输出 faststart（faststart 二次 pass 失败时回退分片）」的策略，保证崩溃/损坏尾部场景不丢产出。
- **前端-取流优先播放版**：视频源优先级从「merge 分片」切换到「faststart 播放版」（若存在），缺失时回退现有 merge 分片路径，保证最低可用。
- **回填现有素材**：对已封存的双摄具（首例 `男双_ct_6949bef776a5` / session `sync_20260720_122645_317228`）补跑一次 `-c copy +faststart` 播放版，使历史素材立即可播。
- 明确**不**为每次分析额外产出 MP4：可播播放版按**录制会话**粒度绑定合并源视频，多个分析共用一份，不随分析次数膨胀。

## Capabilities

### New Capabilities

- `browser-playable-merged-video`: 双摄合并源视频以浏览器可播的 faststart 非分片 MP4 呈现；前端视频源优先消费播放版，缺失时降级到分片 merge；按录制会话粒度生成，多个分析共用。

### Modified Capabilities

<!-- 不改动现有 capability 的需求语义；sync-recording 拖量、tr视频回放分析沿用既有路径，只新增播放版作为首选手码。如需既有 requirement 变更在此补 delta。 -->

## Impact

- 后端：`backend/app/camera/sync_recorder_service.py`（合并/最终化产物生成），可能新增一个「faststart remux」工具函数与对应错误回退；`routes_video.py` / 流式适配（如需识别播放版文件）。
- 前端：`src/components/platform/VideoAnalysisCard.tsx` 取流优先级；`src/pages/VisionPage.tsx` 的 `videoSrc` 选择；`src/services/analysisClient.ts` 取流 URL 构造（如需）。
- 已有素材：回填脚本/一次性任务对 `*_merged.mp4` 补 `-c copy +faststart` 播放版（不重编码、不改源、破坏性无）。
- 测试：后端合并产物单测（分片 + faststart 双产出/回退）、快进播放版原子结构校验（moov 在头、无 moof）；前端取流优先级单测。
- 存储：每会话多一份 faststart 播放版（`-c copy` 近似等体量，无重编码开销）。