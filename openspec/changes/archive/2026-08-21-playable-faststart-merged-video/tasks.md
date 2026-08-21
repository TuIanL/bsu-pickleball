## 1. 后端：合并/最终化产出播放版

- [x] 1.1 在 sync 合并最终化流程（`sync_recorder_service.py`，合并写出并校验 `{camera}_merged.mp4` 之后）追加「生成 `{camera}_playback.mp4`」步骤：`ffmpeg -c copy -movflags +faststart`，temp→校验→`os.replace` 原子落地。
- [x] 1.2 为 remux 增加健壮性 helper（可复用 `run_ffmpeg`）：失败时删除 temp、`warn` 日志、不删除源、不明显抛录制失败；返回是否成功供上层标记播放版缺失。
- [x] 1.3 确认播放版沿用同源 PTS/分辨率语义，不触发重新编码路径（`-c copy`）。

## 2. 后端：视频流接口优先播放版

- [x] 2.1 修改 `routes_video.py` 的 `stream_video`：当 `video.path` 为 `*_merged.mp4` 且同目录存在 `{stem}_playback.mp4` 时，改用它作为返回路径（更新 `filename`/`media_type`）。
- [x] 2.2 保留 Range/206/Accept-Ranges 现有逻辑，播放版判定不误伤非合并视频。
- [x] 2.3 单测：存在播放版返回播放版、缺失回退合并源、普通视频不受影响。

## 3. 回填历史素材

- [x] 3.1 新增脚本 `backend/scripts/backfill_playback_mp4.py`：对给定目录/文件（默认 glob `*_merged.mp4`，支持指定目标）逐个 `-c copy +faststart` 生成 `_playback.mp4`，跳过已存在，失败不删源。
- [x] 3.2 对首例素材（session `sync_20260720_122645_317228`，`174_merged.mp4`/`175_merged.mp4`）运行回填并验证播放版生成。
- [x] 3.3 验证回填后原子结构：播放版 `moov` 在文件头且不含 `moof` 分片（用解析断言）。

## 4. 前端取流与演示验证

- [x] 4.1 确认前端 `VisionPage` 取流逻辑无需改动即可获得播放版（`/api/videos/{video_id}/stream` 服务端解析）。
- [x] 4.2 在浏览器打开 `男双_ct_6949bef776a5` 的数据分析视图，确认视频可播放、进度可拖动、P1·启动回填 框与画面时间对齐。
- [x] 4.3 回归：单摄素材与普通视频流式行为不变。

## 5. 测试与验收

- [x] 5.1 后端单测：`_playback.mp4` 生成与失败降级、流接口解析策略。
- [x] 5.2 仓库级 `pytest` 相关用例与前端 `tsc` 通过（如前端无改动可仅跑后端用例）。
- [x] 5.3 手工验收：新录制（若有）最终化自动产出播放版，浏览器可播。
- [x] 5.4 文档：在相关 merge/最终化处补充「播放版用途」注释。