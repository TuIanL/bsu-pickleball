## Context

当前项目由本地 Vite 前端和本地 FastAPI 后端组成。单摄和双摄已经通过 CaptureTake、CaptureTrack 和统一停止流程关联，但媒体、事件/时间线和分析产物仍分布在不同的默认目录：单摄 Finalizer 存在固定 finalized 路径，双摄服务有独立的默认会话目录，分析服务使用全局 `data/outputs/{job_id}`，事件和标记主要保存在 SQLite。

本变更的约束是：录制位置按单次录制选择，不保存为下次默认值；单摄和双摄必须使用相同的会话目录语义；SQLite 继续作为全局应用索引；移动硬盘中断必须立即结束录制并进入失败状态。用户运行的是本地应用，因此目录选择应通过原生应用桥接完成，而不是依赖浏览器上传目录。

## Goals / Non-Goals

**Goals:**

- 提供跨平台本地原生目录选择器，并把选择结果传给本地后端。
- 默认每次回到标准存储根目录；自定义位置只对当前录制生效。
- 统一生成 `captures/<YYYY-MM-DD>/<capture_take_id>/` 会话目录。
- 将视频、分片、录制元数据、事件、标记、时间线快照和分析产物归档在该会话目录。
- 让 SQLite 保留索引、状态、关系和在线业务查询能力。
- 识别已有 `captures` 目录，避免 `captures/captures`；同一天使用新的 take ID，不能覆盖旧内容。
- 在开始前校验路径，在录制中持续检测目标存储；发现不可写或介质消失时停止并标记失败。
- 使删除、取消、恢复、分析和 artifact API 使用会话记录的实际路径。

**Non-Goals:**

- 不为每次录制创建独立 SQLite 数据库。
- 不把历史默认目录中的旧录制自动迁移到新目录。
- 不支持录制进行中切换存储位置。
- 不实现云端上传、跨设备同步或后台自动复制。
- 不改变单摄/双摄摄像头选择、同步策略和视频编码策略。

## Decisions

### 1. 存储位置由本地应用原生目录选择器提供

前端通过本地应用桥接调用系统目录选择器，返回用户选择的目录路径或受控目录句柄；后端负责解析、规范化和校验实际路径。浏览器 `input type=file`、`webkitdirectory` 和 File System Access API 不作为主方案，因为它们不能稳定地把本机目录授权给后端 FFmpeg 进程。

目录选择 UI 只保存当前页面/当前录制的内存状态，不写入持久配置。空值表示使用 `Settings` 中的标准默认根目录。

### 2. 目录输入统一规范化为存储根目录

后端接收用户选择的目录后执行：

1. 解析绝对路径并消除 `.`、`..` 和重复分隔符。
2. 若选择目录的末级名称为 `captures` 且其父目录可识别，则直接使用该目录。
3. 否则将其解释为存储根目录，并使用 `<root>/captures`。
4. 在目标位置创建或复用 `captures`，不得创建嵌套的 `captures/captures`。
5. 为本次 CaptureTake 创建 `<captures>/<UTC日期>/<capture_take_id>/`，take ID 保证重录和同日多次录制不冲突。

不会根据目录中是否存在旧日期文件夹复制或重建历史数据；只创建当前会话缺失的目录。

### 3. 会话目录是物理文件的唯一归属

每次录制使用以下固定布局：

```text
captures/YYYY-MM-DD/capture_take_id/
├── manifest.json
├── metadata/
│   ├── recording_session.json
│   ├── capture_take.json
│   └── camera_config.json
├── media/
│   ├── cam_1.mp4
│   └── cam_2.mp4
├── fragments/
├── timeline/
│   ├── events.json
│   ├── markers.json
│   ├── segments.json
│   └── live_state.json
└── analysis/
    └── <job_id>/...
```

单摄仅创建和登记一个轨道，双摄创建两个轨道。事件和时间线在录制期间以原子替换或追加安全方式更新，停止时再写最终快照。`manifest.json` 记录 schema 版本、take ID、源 session ID、模式、实际目录、轨道文件和分析任务关联。

### 4. SQLite 是索引，不是媒体归档载体

RecordingSession、CaptureTake、CaptureTrack、TimelineEvent、AnalysisJob 等现有数据库记录继续保存业务状态和可查询关系。新增的存储根目录、会话目录和目录状态引用必须写入相关会话记录或稳定的 metadata 字段。文件归档是 SQLite 记录的物理补充，不在 SQLite 中复制视频或分析 JSON。

如果 SQLite 写入成功但文件快照写入失败，系统记录失败原因并将会话标记为失败；如果文件已写入但数据库更新失败，启动恢复/查询流程必须依据 manifest 和已知 session ID 保留现场，不能静默删除可能可用的媒体。

### 5. 分析任务保留全局 job 索引，产物路径改为会话目录

自动分析任务仍以 `job_id` 在全局任务索引中排队、查询和展示。创建任务时携带 `capture_take_id` 和 `capture_root_dir`，StorageService 根据会话目录解析分析产物路径：`<take_dir>/analysis/<job_id>/...`。旧的全局 `data/outputs/{job_id}` 路径保留只读兼容读取和非录制上传任务支持，新的录制关联任务不再把文件写到旧全局目录。

### 6. 存储中断按不可恢复的本次录制失败处理

开始前检查目录存在、可写、可创建临时文件，并按单摄/双摄预估值检查剩余空间。录制期间由协调器或独立监控任务定期写入/检查会话目录；FFmpeg 写入、分片创建、事件快照或分析归档发现 `ENOENT`、`EIO`、权限错误或介质不可用时：

```text
存储故障
  → 立即停止所有相关 FFmpeg/TrackRecorder
  → 保留已完成片段和 manifest
  → CaptureTake = failed
  → Source Session = failed
  → 释放 CameraLease
  → 禁止自动分析
```

停止操作本身必须幂等，避免故障监控和用户点击停止发生二次终态覆盖。失败响应包含存储路径和可读错误原因，但不把备用默认盘作为隐式回退目标。

### 7. 兼容旧目录和旧会话

已有默认目录中的旧单摄/双摄会话继续按数据库中的 `video_path`、`output_dir` 和 artifact path 读取。新会话使用 manifest 和会话目录字段。删除旧会话仍使用旧路径；删除新会话只允许删除其 manifest 声明且通过路径安全校验的会话树。

## Risks / Trade-offs

- [Risk] 原生目录选择器需要本地应用桥接，单纯运行 Vite 网页时不可用。→ 在应用启动脚本/本地 runtime 提供受控 picker API，并在桥接不可用时明确显示不可用错误，不静默把路径当作默认路径。
- [Risk] 移动硬盘短暂抖动可能被误判为永久故障。→ 对读写错误采用极短的有限确认窗口，但超过窗口立即停止；不长时间阻塞 FFmpeg 或继续写默认盘。
- [Risk] 实时事件与媒体写入竞争导致快照不完整。→ 使用临时文件 + 原子 rename，并在停止/失败收尾时再次生成 manifest 和最终快照。
- [Risk] 分析结果迁移后 API URL 仍以 job_id 为中心。→ API 继续通过 job_id 查索引，再从索引解析实际路径；不把绝对路径直接暴露给前端。
- [Risk] 用户选择的是旧会话目录而非存储根目录。→ 选择器返回后校验目录层级；仅接受存储根或 `captures` 目录，旧会话目录显示引导错误。

## Migration Plan

1. 新增数据库字段和兼容读取逻辑，旧记录缺失字段时根据现有 `video_path`/`output_dir` 推断或标记为 legacy。
2. 上线目录选择、路径规范化和会话目录创建，但默认请求不变，继续使用当前标准目录。
3. 切换单摄、双摄和分析写入到新会话目录，并保留旧路径只读兼容。
4. 完成存储中断、删除、恢复和迁移测试后，再允许正式选择移动硬盘目录。

回滚时，新录制可继续写标准默认目录；已经写入新会话目录的录制不移动，SQLite 中保留实际路径，避免回滚造成数据丢失。

## Open Questions

- 原生目录选择器桥接最终采用当前本地应用的哪种技术实现（已有 runtime API、macOS/Windows 系统桥接，还是新增轻量本地服务）需要在实施前确认。
- 剩余空间阈值需要根据实际码率、录制时长和单摄/双摄配置确定；设计要求执行校验，但具体默认阈值可在实现阶段落定。
