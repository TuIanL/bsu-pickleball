## 0. Spike: 验证 PTS 是否可跨摄像头使用

- [x] 0.1 用当前两台摄像头录制 30 秒和 5 分钟样本，保存原始 RTSP/TS 诊断。
- [x] 0.2 实验关闭 `-use_wallclock_as_timestamps` 的录制命令，比较源 PTS 的 epoch、单调性和跨路差值。
- [x] 0.3 使用 FFmpeg API/ffprobe 验证每路帧级 PTS；确认当前 MPEG-TS 输出 PTS 被归一化，不能直接跨路比较。
- [x] 0.4 根据 spike 结果决定：保留每路局部 PTS，跨路校正必须使用内容同步锚点或已验证时间码，缺失时标记 unknown/degraded。
- [x] 0.5 定义并实现内容同步锚点输入格式（开始/中间/结束事件的两路本地时间或帧号）。

## 1. Source timing artifacts

- [x] 1.1 为每个 TS 分段生成稳定的帧索引/PTS sidecar。
- [x] 1.2 明确源 PTS、主机接收时间、媒体归一化 PTS 的字段含义，禁止混用。
- [x] 1.3 在 `annotation_manifest.json` 中加入 time base、参考机位和映射 artifact。

## 2. Timeline calibration

- [x] 2.1 实现固定偏移 + 线性速率比例的鲁棒拟合。
- [x] 2.2 输出 `offset_ms`、`drift_ppm`、拟合残差、有效区间和质量等级。
- [ ] 2.3 对每个重连分段独立建立映射，保留段间 gap/overlap 诊断。

## 3. Common-timebase outputs

- [x] 3.1 按共同时间网格生成对齐帧索引。
- [x] 3.2 生成可选对齐 MP4，原始 TS 只读保留。
- [x] 3.3 禁止对齐数据缺失时静默回退为 fully aligned。

## 4. Training annotations

- [x] 4.1 将事件时间戳映射到每个摄像头的本地 frame index 和 source PTS。
- [x] 4.2 对超出某一路有效区间的事件输出 unavailable 状态。
- [x] 4.3 增加导出工具，供后续片段切分直接消费。

## 5. Regression and validation

- [ ] 5.1 为固定偏移、线性漂移、丢帧、重复帧和多段重连添加无硬件单测。
- [ ] 5.2 修复并覆盖首尾帧诊断、PTS sidecar 和 manifest 的一致性测试。
- [ ] 5.3 完成 20-30 分钟真实录制，验证起点/中点/终点偏移和拟合残差。
- [ ] 5.4 验证正常停止、异常重启、外接盘 staging 和 MP4 生成失败时原始 TS 不丢失。
