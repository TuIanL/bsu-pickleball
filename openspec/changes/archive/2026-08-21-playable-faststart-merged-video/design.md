## Context

双摄同步录制的合并源视频以分片封装写入（`-movflags +frag_keyframe+empty_moov+default_base_moof`，[sync_recorder_service.py](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/backend/app/camera/sync_recorder_service.py#L2362-L2363)），浏览器原生 `<video>` 无法可靠播放（分片 `moov` 无完整 sample table）。单摄录制仍用 `+faststart` 非分片，浏览器可播。前端 `VisionPage` 的视频源即该合并源（`result.video_id` → `/api/videos/{video_id}/stream`），overlay（P1·启动回填）来自独立 JSON，故视频加载失败时黑底 + 人形框同时出现。

合并发生在录制结束后的 finalize 阶段，此时不再需要分片做崩溃恢复，可以安全地额外产出 faststart 播放版供浏览器流播，无需为每次分析额外生成文件（播放版按会话/机位粒度绑定合并源）。

## Goals / Non-Goals

**Goals:**

- 双摄合并源视频能以浏览器可播的 faststart 非分片 MP4 呈现。
- 流接口在存在播放版时优先返回播放版，缺失时优雅回退。
- 历史分片素材可回填播放版（首例 `男双_ct_6949bef776a5`）。
- 播放版按录制会话粒度一份，随多次分析复用，不膨胀。

**Non-Goals:**

- 不改分片合并源本身（保留其用于分析/崩溃恢复的用途），播放版为独立姐妹文件。
- 不改前端取流逻辑（`/api/videos/{id}/stream` 不变，播放版解析在服务端完成）。
- 不重编码（仅 `-c copy +faststart` 重新封装，帧/PTS/分辨率一致）。

## Decisions

### 决策 1：播放版由合并源 remux 得到，与源并存

在 sync 合并 finalize 写出并校验 `{camera}_merged.mp4` 后，追加一步：`ffmpeg -y -i {merged} -c copy -movflags +faststart {camera}_playback.mp4`。播放版与源并存，源不改动。

- 采用 `-c copy`：不重编码、快、帧/PTS/分辨率与源完全一致 → overlay 时间对齐不受影响。
- 采用姐妹文件而非原地替换：保留分片源供分析管线/诊断使用，可回滚。

### 决策 2：流接口在服务端解析播放版

`routes_video.py` 的 `stream_video` 在定位到 `video.path` 后，若该文件是合并源（`*_merged.mp4`）且同目录存在 `{stem}_playback.mp4`，则改用播放版路径返回。Range/206/Accept-Ranges 逻辑复用现有实现。

- 这样前端完全不用改：`VisionPage` 仍请求 `/api/videos/{video_id}/stream`，服务端自动给可播文件。
- 判定「是合并源」用后缀 `_merged.mp4`，避免误伤普通视频。

### 决策 3：播放版 remux 失败优雅降级

remux 采用「先写 temp→校验→os.replace」原子化；任一步失败则删除 temp、记录 warn、不上报为录制失败，播放版视为缺失（流接口回退分片源，行为与现状一致）。

### 决策 4：回填脚本按会话/目录批量补播放版

新增脚本（如 `backend/scripts/backfill_playback_mp4.py`）：对给定 take 目录（默认支持 glob 所有 `*_merged.mp4`，或指定目标如 `男双_ct_6949bef776a5`）逐个执行 `-c copy +faststart`，跳过已存在播放版，失败不删源。优先回填目标素材，可选全量。

### 决策 5：不引入控制面 per-analysis 文件

播放版在最终化时生成一次，绑定「会话×机位」；分析任务只消费现存的合并源 + 播放版，不为此复制文件。

## Risks / Trade-offs

- [faststart 二次 pass 在损坏尾部的分片输入上可能失败] → remux 失败即跳过（保留分片源），该素材退回「不可播」现状并记 warn；用 `-c copy` 与原子替换降低损坏概率。
- [额外磁盘占用（每机位约一份播放版，`-c copy` 近似等体量）] → 仅按会话粒度，不做 per-analysis；必要时回填可限定目标素材。
- [stream 解析播放版与 timing sidecar 一致性] → remux 不改 PTS/帧，播放版沿用同源 PTS 语义；分析仍读分片源，二者一致。

## Migration Plan

- 部署后端修改后，新双摄录制最终化自动产出播放版。
- 对历史素材运行回填脚本（首例目标 `男双_ct_6949bef776a5` / session `sync_20260720_122645_317228`）。
- 验证：流接口返回播放版（moov 在头、无 moof 分片），比赛库「数据分析」视图可播放且 P1 框对齐。
- 回滚：不起作用时可移除流接口播放版解析（恢复回分片源），不影响其余。

## Open Questions

- 播放版命名统一为 `{camera}_playback.mp4`（与 `{camera}_merged.mp4` 同目录）是否可接受；如需其他后缀在实现前确认。
- 回填默认范围（仅目标素材 vs 全量既有 merge）待确认——默认只回填目标，全量可选。