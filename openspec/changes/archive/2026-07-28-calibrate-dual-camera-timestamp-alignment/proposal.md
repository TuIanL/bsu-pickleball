# 基于真实 PTS 的双摄时间轴校正

## Why

当前双摄 Legacy SyncRecorder 为两路 FFmpeg 都启用 `-use_wallclock_as_timestamps 1`，并在各自进程内执行 `fps=60` CFR 转换。该方案可以生成可播放的两路 TS/MP4，但把 RTSP 原始帧时间戳替换成“主机收到 RTP 包的时间”，无法区分摄像头时钟漂移、网络抖动、解码启动偏移和停止 flush 差异。

真实录制已经观察到：首帧约 50-70ms 的固定偏移，30 分钟后 TS 尾部偏差扩大到约 180ms。MP4 的统一帧数裁剪只能隐藏差异，不能保证中间事件在两路视频中对应同一真实时刻。

## What Changes

- 增加双摄 PTS 可用性探测，确认启用 PTP 后 RTSP 源 PTS 是否共享同一时间基准。
- 录制/诊断链路保留源帧 PTS，并输出每路可供复现的帧时间轴索引。
- 基于两路 PTS 估计固定偏移和线性漂移，生成共同时间轴和校正参数。
- 生成对齐后的派生视频/帧索引，不覆盖原始 TS。
- 扩展 `annotation_manifest.json`，记录每路 PTS 映射、偏移、漂移、置信度和降级原因。
- 多段录制按分段时间轴校正，禁止只使用第一个分段的时长和帧数。
- 对齐数据不可用时显式标记 `sync_quality=unknown/degraded`，禁止静默宣称已同步。

## Capabilities

### New Capabilities

- `dual-camera-timestamp-alignment`：基于真实帧时间戳估计双摄偏移/漂移，并生成共同时间轴与训练标注映射。

### Modified Capabilities

- `capture-take-unified-timeline`：补充双摄 CaptureTrack 的同步质量、偏移和校正产物语义。

## Scope

### In scope

- Legacy SyncRecorder 双摄路径。
- 原始 TS、派生 MP4、CaptureTake/Track 元数据和训练标注清单。
- 单元测试、无摄像头诊断测试和一次真实短录 PTS spike。

### Out of scope

- 实现 Genlock、硬件触发或修改摄像头固件。
- 将副机位直接纳入现有单视频分析流水线。
- 覆盖或删除已有原始 TS。

## Success Criteria

- 能区分固定启动偏移与录制期间漂移。
- 20-30 分钟测试中，对齐后的共同时间轴偏差可量化并可复现。
- 训练数据导出能从事件时间戳得到每个摄像头的本地帧索引，而不是假设两个视频的第 N 帧相同。
