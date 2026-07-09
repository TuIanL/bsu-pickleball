## Context

项目已有现场采集工作流：Field Session 作为采集任务容器，Camera Registry 管理摄像头配置，Recording Session 通过单个 `Recorder` 调 FFmpeg 将一路流录成 MP4，并在停止后可注册视频、创建分析任务。前端 `CaptureConsolePage` 已有摄像头选择、探测、预览、开始/停止录制和事件标记能力。

师哥的独立脚本已经验证了另一套更适合双摄同步的控制模型：每一路摄像头由独立 FFmpeg 进程录制为 `.ts` 分段，主控制线程同时启动所有进程；任一路异常退出或达到分段时长后，控制线程终止所有路并同步进入下一段。这个模型比“两个单摄录制按钮”更适合现场采集，因为开始、停止和异常恢复都必须是一个原子操作。

## Goals / Non-Goals

**Goals:**
- 将双摄同步录制作为后端能力集成进现有 FastAPI 服务，而不是启动独立 Tkinter 程序。
- 支持一次双摄录制会话绑定两个摄像头槽位：主机位 `primary` 和副机位 `secondary`。
- 支持同步开始、同步停止、同步分段、任一路异常后两路同步重启。
- 在前端双摄采集控制台中提供机位选择、探测、短录测试、状态展示和同步录制控制。
- 双摄录制完成后，主机位进入现有分析流程，副机位作为关联素材保存。
- 保持现有单摄录制 API 和用户流程兼容。

**Non-Goals:**
- 不在本次 change 中实现双视角融合算法或双视频联合分析。
- 不要求把所有 `.ts` 分段立即合并为单个 MP4；可先保留分段和主机位登记路径。
- 不重构 Field Session、Camera Registry 或现有单摄 Recorder 的整体架构。
- 不引入新的桌面 GUI；录制操作统一通过 Web 控制台完成。

## Decisions

### D1: 新增独立的 SyncRecording 服务，而不是改造现有 Recorder

现有 `Recorder` 明确管理单个 FFmpeg 进程和单个 MP4 输出，`session_service` 也有全局 `_ACTIVE_CAMERA` / `_ACTIVE_SESSION_ID` 锁。双摄同步需要同时管理多个进程、共享失败事件、分段编号和会话目录，直接塞进单路 `Recorder` 会让单摄路径变复杂。

决策：新增 `SyncRecorder` / `SyncRecordingService`，吸收 `ShouDong.py` 的同步控制循环。单摄继续走现有 `/api/recordings/start`；双摄走新的 `/api/sync-recordings/start`、`/api/sync-recordings/{id}/stop`、`/api/sync-recordings/{id}/test` 等 API。

替代方案：复用现有 Recording Session 创建两条普通会话并同时调用开始。否决，因为无法保证同步停止、异常时全路重启，也难以表达“这是同一次双摄采集”。

### D2: 双摄录制会话是一个顶层对象，内部包含两路机位和分段

双摄录制从产品语义上是一件事：用户点击一次开始，系统同时录两路；用户点击一次停止，系统同时结束两路。因此数据模型应以 `SyncRecordingSession` 为顶层对象。

建议字段：
- `session_id`
- `field_session_id`
- `status`: `recording | completed | failed | canceled`
- `camera_slots`: `primary` / `secondary`，每个包含 `camera_id`、`camera_angle`、`stream_url_snapshot`
- `segments`: 每段包含 `segment_index`、每路文件路径、开始/结束时间、状态
- `output_dir`
- `primary_video_id`
- `associated_video_paths`
- `error_message`

替代方案：把双摄结果写成两个 `RecordingSession` 并用相同 group id 关联。暂不采用，因为现有 `RecordingSession` 只有单个 `camera_id` 和 `video_path`，会让 API 响应和前端状态难以表达同步分段。

### D3: 第一阶段保留 `.ts` 分段，主机位可后处理接入分析

师哥脚本使用 `-c copy -f mpegts`，优点是低开销、稳定、适合 RTSP 原始流保存；缺点是现有 VideoService 和分析入口更偏向单个上传视频文件。

决策：双摄录制文件先按分段保存为 `.ts`，停止时登记主机位可用产物。若当前 VideoService 不接受 `.ts`，实现阶段可以增加“主机位合并/转码为 MP4”的轻量后处理，或先仅在完成面板展示文件路径并禁用自动分析。规范上要求主机位能接入现有分析流程，允许实现选择合并或转码方式。

替代方案：录制时直接输出 MP4。否决作为默认方案，因为 RTSP 中断或强制重启时 MP4 收尾更脆弱，且与已有同步脚本稳定路径偏离较大。

### D4: 前端使用机位槽位选择，而不是一个全局 selectedCameraId

当前控制台只有一个 `selectedCameraId`，双摄需要表达“底线高机位”和“侧面机位”两个槽位，并防止同一摄像头被重复选择。

决策：当 `fieldSession.camera_setup === "dual"` 时，控制台维护 `selectedCameraSlots`，例如：

```json
{
  "primary": "camera-a",
  "secondary": "camera-b"
}
```

选择结果先用 `sessionStorage` 兜底持久化；后续如需要跨设备恢复，可再扩展后端 Field Session metadata。

替代方案：在向导中强制选择两路摄像头。暂不强制，因为当前设备注册和探测更适合在控制台完成，现场调试也常需要临时更换机位。

### D5: 短录测试复用同步录制核心，但不创建正式采集结果

双摄现场风险主要在开录前：RTSP 地址错误、两路网络不稳、FFmpeg 不可用、首尾帧无法读出。短录测试需要尽量走真实录制路径。

决策：新增短录测试 API，接收两个摄像头槽位和测试时长，调用同步录制核心录制短分段，提取首帧/尾帧和基础状态，结果标记为 `test`，不进入正式 Recording/Analysis 列表。

替代方案：只调用现有 `probeCamera`。否决作为唯一测试方式，因为 probe 只能证明能读到帧，不能验证同步 FFmpeg 录制、输出文件和分段收尾。

## Risks / Trade-offs

- [Risk] 两路 FFmpeg 同步启动仍存在毫秒级偏差。→ Mitigation：主控制线程同时创建进程并记录每段启动时间；前端表述为“同步控制录制”，不承诺帧级硬同步。
- [Risk] 任一路异常导致两路同步重启，可能产生多个短分段。→ Mitigation：在会话 metadata 中清晰记录分段编号、失败原因和重启次数，前端展示分段状态。
- [Risk] `.ts` 分段不一定能直接进入现有分析流程。→ Mitigation：实现主机位 MP4 合并/转码或在完成面板延迟启用分析入口，确保不会误导用户。
- [Risk] 全局录制锁从单摄扩展到双摄后可能出现互相抢占。→ Mitigation：双摄开始前检查两个摄像头都没有活跃单摄/双摄会话；双摄进行中禁止删除或再次使用相关摄像头。
- [Risk] 现场网络波动导致短录测试通过但正式录制失败。→ Mitigation：正式录制继续保留异常重启机制，并在 UI 中显示重启次数和最近错误。

## Migration Plan

1. 新增双摄同步录制模型、服务和 API，不修改现有单摄 API 行为。
2. 前端仅在 `camera_setup=dual` 时启用双摄控制台；单摄任务继续使用现有流程。
3. 双摄会话 metadata 写入新的目录，避免影响 `data/recordings/sessions` 的旧格式。
4. 验证稳定后，可在采集任务列表中补充双摄会话摘要。
5. 回滚时关闭双摄入口即可，已有单摄录制不受影响。

## Open Questions

- 主机位默认应固定为底线高机位，还是允许用户在完成后选择用于分析的机位？
- 主机位 `.ts` 分段合并为 MP4 是本 change 必做，还是允许先保存分段、后续单独加合并任务？
- 双摄录制的副机位素材未来是否需要进入分析任务 metadata，为双视角算法预留字段？
