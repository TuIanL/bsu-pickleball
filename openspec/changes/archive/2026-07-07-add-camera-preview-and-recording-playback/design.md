## Context

项目已经具备摄像头注册、在线探测、FFmpeg 录制、录制 session 持久化、`VideoService.register_recording()` 和 `/api/videos/{video_id}/stream` 视频播放接口。当前缺口在用户体验层：录制前看不到摄像头实时画面，录制后无法从历史列表直接回看视频。

浏览器不能直接播放常见 RTSP 摄像头流，因此实时预览需要后端做协议转换。录制回放则不需要新存储系统，完成录制时已有 `video_id` 可以接入现有视频流接口。

## Goals / Non-Goals

**Goals:**
- 在球场采集页面根据当前选择的摄像头展示实时预览画面。
- 为预览提供明确的加载、可用、失败、未选择状态。
- 在录制历史中为已完成且可播放的录制提供播放入口。
- 复用 `VideoService` 和现有视频 stream API 播放录制视频。
- 保持当前单路录制模型，不改变录制 session 状态机。

**Non-Goals:**
- 不做 WebRTC、HLS、低延迟多观众直播或公网转发。
- 不做多路摄像头同时预览的复杂调度。
- 不在预览链路中进行 AI 分析或姿态/轨迹叠加。
- 不为失败或取消的录制强行生成可播放视频。
- 不引入数据库或新的持久化系统。

## Decisions

| 决策 | 选择 | 理由 | 备选方案 |
|------|------|------|----------|
| 实时预览协议 | MJPEG over HTTP (`multipart/x-mixed-replace`) | 浏览器可用 `<img>` 直接展示；后端可用 OpenCV 读取帧并 JPEG 编码；实现轻量，适合本地球场调试 | WebRTC 延迟更低但需要 signaling/媒体管线；HLS 更稳定但延迟高且实现更重；定时抓单帧太卡顿 |
| 预览读取方式 | 后端按请求打开 `cv2.VideoCapture`，断开时释放 | 与现有探测逻辑一致，避免共享全局 capture 的生命周期复杂度 | 全局共享预览 worker 可降低摄像头连接数，但需要订阅管理和缓存 |
| 预览帧率 | 第一版限制在低帧率，例如 5-10 FPS | 足以确认角度和画面，降低 CPU、网络和摄像头压力 | 原始帧率预览会增加资源占用 |
| 预览画质 | JPEG 编码并可设置固定质量 | 兼容性高，浏览器无需额外播放器 | 转码为 MP4/HLS 更重，且不适合即时预览 |
| 回放入口 | 历史列表按钮打开内嵌播放器或弹窗 | 用户在同一页面完成采集和检查；不需要跳转到分析页 | 跳转到独立视频页面会增加导航复杂度 |
| 回放数据源 | `getVideoStreamUrl(session.video_id)` | 已有 `/api/videos/{video_id}/stream` 能直接被 `<video controls>` 播放 | 直接暴露 `video_path` 不安全且绕过视频服务 |

## API Sketch

### 摄像头预览

```
GET /api/cameras/{camera_id}/preview
Accept: multipart/x-mixed-replace
```

行为：
- 摄像头不存在时返回 404。
- 摄像头无法打开或读帧失败时返回合适的错误响应，前端显示预览失败状态。
- 成功时持续返回 JPEG 帧，响应类型为 `multipart/x-mixed-replace; boundary=frame`。
- 客户端断开连接时释放 `VideoCapture`。

### 录制回放

不新增后端视频播放端点，继续使用：

```
GET /api/videos/{video_id}/stream
```

前端只在 `session.status === "completed"` 且 `session.video_id` 存在时展示播放入口。

## UI Flow

```
选择摄像头
   │
   ▼
预览区域加载 /api/cameras/{camera_id}/preview
   │
   ├─ 成功：显示实时画面
   └─ 失败：显示错误状态和重试入口

停止录制
   │
   ▼
session.status = completed
session.video_id = rec-xxxx
   │
   ▼
录制历史显示「播放」
   │
   ▼
<video controls src="/api/videos/rec-xxxx/stream" />
```

## Risks / Trade-offs

- [Risk] MJPEG 预览每个浏览器连接都会读取并编码帧，长时间打开会占用 CPU 和摄像头资源。→ Mitigation：限制帧率和 JPEG 质量，前端在未选择摄像头或组件卸载时断开预览。
- [Risk] 某些 RTSP 摄像头只允许一个客户端连接，预览和录制同时连接可能冲突。→ Mitigation：第一版明确记录该限制；如果真实设备冲突，后续改为 FFmpeg tee 或共享读取 worker。
- [Risk] OpenCV 打开 RTSP 失败时错误信息可能不够友好。→ Mitigation：前端提供通用恢复建议，后端记录具体异常供调试。
- [Risk] 录制文件已经注册但磁盘文件缺失时播放会 404。→ Mitigation：播放按钮触发失败状态；历史列表仍保留 session 元数据用于排查。
- [Risk] Safari/Chrome 对 MJPEG 的连接行为不同。→ Mitigation：用标准 `<img>` 加载并在主流浏览器做本地验证；必要时提供手动刷新预览。

## Migration Plan

- 新增 API 和前端 UI 均为增量功能，不需要数据迁移。
- 已存在的 completed session 只要有 `video_id`，即可在新 UI 中播放。
- 如果预览 API 出现问题，可隐藏前端预览区域或让其显示失败状态，不影响录制控制和历史列表。

## Open Questions

- 实际摄像头是否允许预览和录制同时连接同一路 RTSP 流？需要用目标设备验证。
- 预览默认帧率和 JPEG 质量需要在真实网络环境中微调。
