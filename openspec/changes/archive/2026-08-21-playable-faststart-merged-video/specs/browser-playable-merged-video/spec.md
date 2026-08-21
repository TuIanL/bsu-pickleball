## ADDED Requirements

### Requirement: 双摄合并源视频产出浏览器可播播放版

系统 SHALL 在双摄同步录制的合并/最终化阶段，为每个机位的合并源视频（`{camera}_merged.mp4`）额外产出一个 faststart 非分片播放版（`{camera}_playback.mp4`），使浏览器原生 `<video>` 可直接播放。播放版 SHALL 通过 `ffmpeg -c copy -movflags +faststart` 由合并源重新封装得到（不重编码），因此帧、时间戳、分辨率与原源一致。

#### Scenario: 合并完成后补齐播放版

- **WHEN** 双摄录制会话在某机位写入了完成合并、且可解码验证通过的 `{camera}_merged.mp4`
- **THEN** 系统 SHALL 尝试生成同目录下的 `{camera}_playback.mp4`（faststart 封装）
- **AND** 生成过程中源 `{camera}_merged.mp4` 不得被修改或删除

#### Scenario: 播放版 remux 失败时优雅降级

- **WHEN** 对某个合并源执行 faststart 重新封装失败（如损坏尾部）
- **THEN** 系统 SHALL 保留原分片合并源，不删除任何文件
- **AND** 记录警告日志，该会话播放版标记为缺失，后续按缺失降级处理

#### Scenario: 每次分析方法均不复用额外文件

- **WHEN** 用户对同一段录制发起多次分析
- **THEN** 播放版按录制会话粒度存在一份，SHALL NOT 随分析次数重复生成或复制

### Requirement: 视频流接口优先返回播放版

`GET /api/videos/{video_id}/stream` SHALL 在目标视频为分片合并源时，优先返回同会话的 faststart 播放版文件；播放版缺失时回退到原合并源，保证浏览器最低限度可流式接收。

#### Scenario: 存在播放版时返回播放版

- **WHEN** 请求流式服务一个分片合并源视频，且同目录存在 `{stem}_playback.mp4`
- **THEN** 响应 SHALL 返回该播放版文件（支持 Range / 206 / Accept-Ranges）
- **AND** 返回内容为浏览器可解码的 faststart MP4，而非分片封装

#### Scenario: 播放版缺失时回退合并源

- **WHEN** 请求流式服务一个分片合并源视频，但不存在对应 `{stem}_playback.mp4`
- **THEN** 响应 SHALL 回退返回原合并源文件，且行为与现状一致

#### Scenario: 非合并普通视频不受影响

- **WHEN** 请求流式服务一个非分片/非合并视频
- **THEN** 响应 SHALL 直接返回原文件，不引入播放版解析逻辑

### Requirement: 历史分片素材可回填播放版

系统 SHALL 提供回填能力，对已封存的、缺失播放版的合并源视频补生成 `{camera}_playback.mp4`，使历史双摄素材在浏览器可播。

#### Scenario: 后台回填已有分片合并源

- **WHEN** 对 `{camera}_merged.mp4` 执行回填（生成其 `_playback.mp4`）
- **THEN** 生成失败不删除源、成功则不改变原源文件
- **AND** 回填不依赖分析任务，仅依赖合并源文件本身

#### Scenario: 回填后浏览器可播

- **WHEN** 一个此前无法在浏览器播放的历史双摄素材完成回填并刷新
- **THEN** 其在比赛库「数据分析/视频」视图可正常播放，且 overlay（如 P1·启动回填）与画面时间对齐