## Context

当前系统已经在多处记录或读取 FPS，但语义不统一：

- 录制模型 `RecordingStartRequest` / `SyncStartRequest` 已有 `fps` 字段，范围为 1~120，但前端单摄启动写死 90，双摄启动写死 30。
- 上传分析页面没有让用户确认 FPS；后端分析主要读取 `cv2.CAP_PROP_FPS`，读取失败时多处回退到 30。
- 分析配置中存在大量 frame-based 时间窗口，例如 `primary_player_window_frames=90`、`player_identity_lost_buffer_frames=90`、`ball_stationary_blacklist_frames=60`。这些值在不同 FPS 下代表不同真实时长。
- 当前进行中的 `smooth-minimap-player-motion` change 已经将部分渲染插值和拖尾配置改为秒语义，本 change 需要与其保持同一个 FPS 来源。

本变更的核心约束是：后端计算时必须依据真实 FPS。这里的“真实 FPS”不是硬编码默认值，而是任务运行时解析出的 `effective_fps`，并且所有时间敏感模块使用同一个值。

## Goals / Non-Goals

**Goals:**

- 上传视频和实时录制界面都允许用户选择/确认源视频 FPS。
- 分析任务保存用户确认的 FPS，并在 job metadata、任务签名和结果 source metadata 中可追踪。
- 后端分析流水线统一计算 `effective_fps`，并把它传递给 tracking、identity、player lock、ball tracking、bounce detection、overlay 和 visualization。
- 把关键 frame-based 时间窗口改为秒语义或提供秒语义派生层，确保 30/60/90/120fps 下真实时间行为一致。
- 保留视频 metadata FPS 的自动读取能力，但允许用户确认值覆盖错误或缺失的 metadata。
- 从录制视频创建分析任务时，用录制 session FPS 预填并允许提交。

**Non-Goals:**

- 不改变视频文件本身的编码帧率，不强制 FFmpeg 重采样或补帧。
- 不实现浏览器端精确 FPS 探测算法；浏览器只能辅助显示已知/推断信息，最终以后端/用户确认值为准。
- 不重新训练模型或改变检测模型权重。
- 不在本 change 中完成 `smooth-minimap-player-motion` 的全部轨迹后处理实现，但要保证其读取的 FPS 来源一致。

## Decisions

### D1: 新增用户确认的源 FPS 字段

在分析任务元数据或 pipeline options 中新增 `sourceFps`（后端可用 `source_fps`）字段，类型为正数，建议范围 1~240，前端常用选项限制在 24/25/30/50/60/90/120 和自定义。

**Rationale:** FPS 是源素材属性，属于创建分析任务时必须保存的输入。放入任务输入后可以参与签名、审计和复跑。

**Alternatives considered:**

- 只依赖 OpenCV metadata：无法处理 metadata 缺失、错误、可变帧率近似值异常。
- 只放在前端 local state：任务复跑、后台 worker 和结果产物无法追踪。

### D2: 后端统一计算 `effective_fps`

分析流水线进入视频读取阶段后计算：

```text
effective_fps =
  valid(user_source_fps) ? user_source_fps :
  valid(video_metadata_fps) ? video_metadata_fps :
  30.0
```

`valid(fps)` 表示数值有限且大于 0。结果写入 tracking result、overlay artifact、ball artifact、analysis source metadata 和诊断信息。若用户确认 FPS 与 metadata FPS 差异超过阈值（例如 5%），诊断中记录 `fps_source=user_override` 和 metadata 值。

**Rationale:** 所有后端模块必须共享同一个 FPS，避免不同阶段各自 fallback。

**Alternatives considered:**

- 每个模块各自读取 video metadata：容易出现 tracking、ball、overlay 计算使用不同 FPS。
- 修改视频 metadata 后再分析：会改变源文件语义，且对上传文件和录制文件都更重。

### D3: 时间窗口以秒为配置语义

新增内部 helper，例如：

```python
def frames_for_seconds(seconds: float, fps: float, *, minimum: int = 1) -> int:
    return max(minimum, int(round(seconds * max(fps, 1.0))))
```

优先把关键配置改成 seconds 字段：

| 当前配置 | 建议 seconds 语义 |
| --- | --- |
| `primary_player_window_frames=90` | `primary_player_window_seconds=1.0`（若现有真实意图是 90fps 下约 1 秒） |
| `player_identity_lost_buffer_frames=90` | `player_identity_lost_buffer_seconds=1.0` |
| `player_identity_inactive_buffer_frames=180` | `player_identity_inactive_buffer_seconds=2.0` |
| `player_identity_interpolation_buffer_frames=90` | `player_identity_interpolation_buffer_seconds=1.0` |
| `ball_stationary_blacklist_frames=60` | `ball_stationary_blacklist_seconds=2.0`（沿用现有文档“约 2 秒 @30fps”） |
| `player_lock_bootstrap_min_frames=60` | `player_lock_bootstrap_min_seconds=1.0` 或按现有行为审定 |
| `player_lock_bootstrap_max_frames=180` | `player_lock_bootstrap_max_seconds=3.0` 或按现有行为审定 |
| `player_lock_lost_max_frames_locked=300` | `player_lock_lost_max_seconds=10.0`（沿用现有注释） |

保留旧环境变量读取作为兼容：如果 seconds 环境变量不存在但 frames 环境变量存在，可按 reference FPS 30 或 90 转成 seconds，并在配置诊断中标记 legacy。

**Rationale:** 用户关心的是“丢失后等 1 秒”“静止 2 秒”，不是固定 60/90 帧。

**Alternatives considered:**

- 保留 frames 配置并在每处手写比例缩放：实现分散，容易漏项。
- 直接把 90 改成 30：只能修一类素材，不能适配 60/120fps。

### D4: 录制 FPS 表示“用户声明/设备目标”，不强制重编码

实时录制开始请求继续携带 `fps`，前端不再写死。Recorder 保持 stream copy/passthrough，不为了匹配用户选择而强制 `-r` 重编码。停止录制后注册视频时保存 session FPS，创建分析任务时作为默认 `sourceFps`。

**Rationale:** 现有注释已经说明重编码 1080p/90fps 可能导致性能和卡顿问题。FPS 字段用于分析解释和 session metadata，不应强行改变视频码流。

**Alternatives considered:**

- FFmpeg 强制 `-r <fps>`：可能补帧/丢帧，影响动作分析真实性。
- 完全忽略录制 FPS：从录制进入分析时无法预填用户已知的设备帧率。

### D5: 上传分析 UI 显示“检测值 + 用户确认值”

上传文件后，若后端视频 metadata 可用，UI 可显示检测 FPS；录制视频则从 recording session 预填 FPS。用户仍可改选。提交时必须携带 `sourceFps`。

**Rationale:** 用户经常比 metadata 更清楚设备设置，尤其是导出、转码或监控流录制场景。

**Alternatives considered:**

- 让用户只在 metadata 缺失时输入：无法处理 metadata 错误。

### D6: 任务签名包含 FPS

`analysis_signature()` 的 input/config payload 必须纳入 `sourceFps` 或 normalized `effective_fps` 来源信息。相同视频、标定但不同 FPS 的任务不能被视为同一任务。

**Rationale:** FPS 会改变时间戳、速度、事件间隔和轨迹结果，是分析输入的一部分。

**Alternatives considered:**

- 不纳入签名：用户修改 FPS 后可能复用旧结果。

### D7: 与小地图平滑 change 对齐

`smooth-minimap-player-motion` 中的 `build_tracks(observations, events, fps, total_frames)`、`trail_seconds` 和 overlay 渲染必须使用本 change 产生的同一个 `effective_fps`。

**Rationale:** 小地图平滑本质上依赖真实时间间隔，如果用不同 FPS 会重新出现卡顿或速度不一致。

## Risks / Trade-offs

- [Risk] 用户选择的 FPS 与视频真实帧时间不一致，分析仍会偏差。  
  → Mitigation: UI 显示 metadata FPS，后端诊断记录 user/metadata 差异，结果 source metadata 标明 `fps_source`。

- [Risk] 可变帧率视频无法被单一 FPS 完美描述。  
  → Mitigation: 本 change 仍以恒定 effective FPS 为分析基准；后续可扩展 per-frame PTS 支持。

- [Risk] 旧环境变量以 frames 为单位，直接改名会影响部署。  
  → Mitigation: 保留旧变量兼容，并新增 seconds 变量优先级。

- [Risk] 影响模块较多，容易漏掉某个 fallback。  
  → Mitigation: 新增集中 helper 和测试清单，要求 30/60/90/120fps 用例覆盖 tracking、identity、ball、bounce、overlay metadata。

- [Risk] 录制 FPS 是用户声明值，实际摄像头可能输出不同 FPS。  
  → Mitigation: 分析创建页允许用户确认/修改；后端读取 metadata 并记录差异。

## Migration Plan

1. 增加 schema 字段和前端类型，默认使用 30fps 保持旧任务可解析。
2. 增加 UI FPS 控件，录制入口从用户选择值生成 request，上传入口从 metadata/recording session 预填。
3. 后端 job orchestration 保存并传递 `source_fps`，签名纳入 FPS。
4. Pipeline 增加 `effective_fps` helper，替换 `raw_fps`/`fps if fps > 0 else 30.0` 的分散 fallback。
5. 将关键 frame-based 配置增加 seconds 派生层，逐步替换传入 manager/tracker 的帧数。
6. 补充测试并验证旧 demo/旧任务 metadata 缺失时仍能 fallback 到 30fps。

Rollback 时可保留新增字段但忽略，由后端继续读取视频 metadata；前端默认 FPS 控件不影响旧 API 的解析。

## Open Questions

- `primary_player_window_frames=90` 的真实意图是 90fps 下 1 秒，还是 30fps 下 3 秒？实现前需要结合当前算法表现确认默认 seconds。
- 是否需要把 `sourceFps` 允许到 240fps，以覆盖部分手机慢动作素材，还是保持录制请求 1~120、上传分析 1~240？
- 是否在上传后立即调用后端 metadata endpoint 读取 FPS，还是先在创建任务时由后端统一读取并返回诊断？
