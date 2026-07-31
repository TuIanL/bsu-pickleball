# Design

## Current Flow

```text
RTSP A ──> FFmpeg A (-use_wallclock, fps=60) ──> A.ts ──> MP4 crop
RTSP B ──> FFmpeg B (-use_wallclock, fps=60) ──> B.ts ──> MP4 crop
                         │
                         └── input_start_time + duration -> common frame count
```

当前的 `input_start_time` 是 FFmpeg 看到的 RTSP 首包墙钟时间，`media_start_time_sec` 在 MPEG-TS 中通常没有跨摄像头含义。该数据可以用于近似固定偏移，但不能测量全程漂移。

## Goals / Non-Goals

**Goals:**

- 验证并保留可跨摄像头比较的源 PTS（若设备确实提供）。
- 将固定启动偏移、时钟漂移、分段 gap/overlap 和帧选择误差显式化。
- 生成可供回放和训练使用的共同时间轴派生物，同时保留原始 TS。

**Non-Goals:**

- 不把普通 NTP 或 PTP 校时误认为硬件 Genlock/硬件触发。
- 不在本 change 中实现摄像头固件、网络交换机或硬件同步设备改造。
- 不让校正失败的素材被标记为 fully aligned。

## Target Flow

```text
RTSP A ──> source PTS/frame index ──┐
                                    ├─> PTS probe + affine fit
RTSP B ──> source PTS/frame index ──┘          │
                                               ▼
                                 common time grid (60 fps)
                                               │
                       ┌───────────────────────┴──────────────────────┐
                       ▼                                              ▼
                 aligned media                               annotation manifest
```

## Phase 0: PTS Spike

在修改正式录制前，使用相同两台摄像头做短录对照：

1. 现有墙钟模式录制一组，记录当前行为；
2. 关闭 `-use_wallclock_as_timestamps 1`，保留 RTSP 源 PTS 录制一组；
3. 用 PyAV/FFmpeg API 读取每路解码帧的 `pts * time_base`；
4. 检查两路 PTS 是否共享同一 epoch、是否单调、是否在 20-30 分钟内保持稳定斜率。

若源 PTS 不是共享时钟，PTS 只能用于每路内部排序，不能直接用来跨摄像头同步；此时必须保留内容同步标记或使用硬件同步，不应假装 PTS 已解决问题。

### Spike 结果（2026-07-19）

对两台摄像头做了 30 秒、关闭 `-use_wallclock_as_timestamps` 的 RTSP copy spike：两路输出 TS 的 `time_base` 均为 `1/90000`、`start_pts=126000`、`start_time=1.4s`，首包/末包 PTS 约为 `1.4s -> 31.38s`。这证明当前 MPEG-TS 输出 PTS 是各文件内部归一化时间轴，不是可直接跨摄像头比较的共享 epoch。

因此本 change 不会把归一化 PTS 自动判定为跨路同步依据。它们仍会作为每路帧索引和局部时间轴保存；跨路 `offset/drift` 必须来自内容同步锚点、已验证的设备时间码，或明确标记为 `unknown/degraded`。

## PTS Model

选定参考机位 `ref` 后，对另一机位拟合：

```text
t_camera = offset_seconds + rate * t_ref
```

- `offset_seconds` 表示固定启动偏移；
- `rate - 1` 表示相对时钟速率差；
- 使用鲁棒拟合，剔除丢帧、重复帧和重连段的异常点；
- 每个分段独立保留原始 PTS，再将分段映射到 take 时间轴，不能把重连后的间隙直接 concat 抹平。

## Common Grid

输出时间轴为 `n / target_fps`，默认 `target_fps=60`。每个目标时刻选择校正后 PTS 最近的源帧，并记录：

- `source_frame_index`；
- `source_pts`；
- `target_time_ms`；
- `selection_error_ms`；
- `dropped/duplicated` 状态。

原始 TS 保持只读。对齐 MP4 或帧索引是派生物，失败时保留原始素材并报告原因。

## Artifacts

```text
174_s1.ts / 175_s1.ts                 原始素材
174_frame_pts.jsonl / 175_frame_pts.jsonl  每帧 PTS 索引
174_aligned.mp4 / 175_aligned.mp4     共同时间轴派生视频
timeline/annotation_manifest.json     事件到各机位帧的映射
timeline/sync_calibration.json        offset/rate/quality/diagnostics
```

`annotation_manifest.json` 每路 source 至少包含：`camera_id`、`video_id`、原始路径、`offset_ms`、`drift_ppm`、`reference_camera`、`sync_quality`、`mapping_artifact`。

## Failure Policy

- PTS 缺失或不单调：`sync_quality=unknown`，不生成“已对齐”声明；
- 拟合残差超过阈值：`sync_quality=degraded`，保留诊断和内容同步建议；
- 多段之间无法建立映射：禁止将全部分段简单 concat 后使用第一段的 `target_frames`；
- MP4 生成失败：不删除 TS，前端展示明确的校正失败原因。

## Risks / Trade-offs

- [源 PTS 不共享时间基准] -> 先做 PTS spike；失败时降级为内容同步标记或明确 unknown。
- [逐帧 sidecar 增加存储和 IO] -> JSONL 使用紧凑字段，允许按需生成并保留关键诊断摘要。
- [重采样可能丢帧或复制帧] -> 记录 source frame、selection error 和 dropped/duplicated 状态。
- [长视频重编码耗时] -> 原始 TS 立即可用；对齐 MP4 作为异步派生物，不阻塞原始归档。

## Migration Plan

1. 先以 spike 结果确认源 PTS 方案，不改变现有 TS/MP4 默认产物。
2. 增加 sidecar 和 manifest 字段，旧录制缺失字段时按 `unknown` 兼容读取。
3. 开启共同时间轴派生物的灰度输出，保留现有回放路径作为回退。
4. 经过 20-30 分钟真实录制验证后，再将训练导出切换到校正映射。
5. 回滚时停止生成派生校正物，继续保留原始 TS 和现有 MP4 裁剪流程。

## Key Decisions To Confirm

1. PTS spike 已证明当前 TS PTS 不可直接跨设备比较；是否接入可见同步锚点作为校准输入；
2. 对齐派生物优先输出 MP4，还是优先输出每帧索引供训练切片使用；
3. 允许的最大残差：严格 1 帧（16.7ms）还是工程阈值 2 帧（33.3ms）；
4. 是否要求每次录制必须有开始/中间/结束的可见同步动作作为 PTS 校验锚点。
