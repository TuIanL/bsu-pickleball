## 1. 原生目录选择与路径契约

- [x] 1.1 调查当前本地 runtime/启动方式，确定原生目录选择器桥接接口及 macOS/Windows 的实现边界
- [x] 1.2 实现本地应用原生目录选择器调用，返回规范化的用户选择目录，并在桥接不可用时返回明确错误
- [x] 1.3 为单摄和双摄录制请求增加可选 `storage_root`，并在会话响应中暴露逻辑化的 storage root/session directory 引用
- [x] 1.4 实现路径规范化：识别已存在的 `captures` 目录，禁止 `captures/captures`，拒绝旧录制会话目录作为新根目录
- [x] 1.5 实现目标目录可访问、可写、可创建临时文件和剩余空间校验

## 2. 数据模型与会话目录

- [x] 2.1 为 RecordingSession、SyncRecordingSession/CaptureTake 增加存储根目录、会话目录和存储状态字段及兼容序列化
- [x] 2.2 编写数据库迁移；保证历史记录缺失新字段时继续按旧 video_path/output_dir/artifact path 读取
- [x] 2.3 实现统一的 `captures/YYYY-MM-DD/<capture_take_id>/` 目录规划器和 manifest schema
- [x] 2.4 实现 metadata、media、fragments、timeline、analysis 子目录创建与安全路径校验
- [x] 2.5 实现 manifest 和 metadata 的原子写入、更新及失败现场保留

## 3. 单摄录制路径接入

- [x] 3.1 将单摄 session_service、CaptureRuntimeCoordinator 和 TrackRecorder 的分片输出改为当前 CaptureTake 会话目录
- [x] 3.2 移除单摄 Finalizer 对固定 `data/recordings/finalized` 的写入依赖，改为从会话目录生成最终视频并注册 Video
- [x] 3.3 在单摄启动前完成目录校验和 CaptureTake/Session 存储目录登记，目录失败时不启动 FFmpeg
- [x] 3.4 在单摄停止、取消和恢复流程中按实际会话目录完成收尾、清理和结果构建
- [x] 3.5 增加单摄默认目录、自定义移动硬盘目录、同日多次录制和旧会话兼容测试

## 4. 双摄录制路径接入

- [x] 4.1 将双摄同步服务的默认 output_dir 改为使用统一会话目录规划器
- [x] 4.2 让双摄两路分片、合并视频、轨道元数据和 manifest 全部写入同一 CaptureTake 会话目录
- [x] 4.3 在双摄启动前执行双路所需空间检查，并在目录创建失败时释放两路 Lease 且不启动 FFmpeg
- [x] 4.4 在双摄停止、取消、恢复和删除流程中使用记录的实际 output_dir/session directory
- [x] 4.5 增加双摄目录结构、历史目录复用、同日多次录制和双路失败清理测试

## 5. 事件、标记与时间线归档

- [x] 5.1 增加 timeline events、markers、segments、live state 的会话目录序列化格式和版本字段
- [x] 5.2 将实时 CodingAction/Outbox 投影后的事件和时间线以原子方式同步写入当前会话目录，同时保留 SQLite 索引
- [x] 5.3 在正常停止和失败停止时生成最终事件、标记和时间线快照，并更新 manifest
- [x] 5.4 增加页面刷新、Outbox 迟到事件、停止超时和事件文件写入失败的测试

## 6. 分析产物路径与索引

- [x] 6.1 扩展分析任务创建和执行上下文，携带 capture_take_id 与实际会话目录
- [x] 6.2 修改 StorageService 和分析 pipeline，使录制关联任务写入 `<take_dir>/analysis/<job_id>/`
- [x] 6.3 保留无 CaptureTake 的上传任务和历史任务使用全局 `outputs/<job_id>/` 的兼容路径
- [x] 6.4 让 AnalysisPipelineResult、artifact API 和前端展示通过 SQLite 索引解析逻辑 artifact 引用，不暴露绝对路径
- [x] 6.5 增加视频、JSON、JSONL、图像和分析叠加视频均位于会话目录的测试

## 7. 存储中断与状态收尾

- [x] 7.1 实现录制期间会话目录可写性/介质状态监控，并识别介质消失、ENOENT、EIO 和权限错误
- [x] 7.2 实现存储故障的统一停止流程：停止所有相关轨道、保留已有文件、写失败 manifest、CaptureTake/Session 标记 failed、释放 Lease
- [x] 7.3 禁止存储故障后自动回退默认目录或触发自动分析，并向停止/查询 API 返回可理解的错误原因
- [x] 7.4 保证用户停止、故障监控和恢复轮询之间终态更新幂等，不覆盖已有 failed/completed/partial 终态
- [x] 7.5 增加拔出移动硬盘、目录权限变化、空间耗尽和故障后恢复查询的单元/集成测试

## 8. 前端录制设置与验证

- [x] 8.1 在单摄和双摄摄像头选择旁增加录制位置选项，展示默认位置和当前临时选择
- [x] 8.2 接入原生目录选择器，允许清除自定义选择并恢复当前默认位置；不持久化上一次自定义路径
- [x] 8.3 将当前录制位置加入 CaptureStartIntent，并在启动前显示目录不可用、空间不足等错误
- [x] 8.4 在录制控制台、停止结果和失败状态中展示会话目录逻辑引用及存储故障信息
- [x] 8.5 增加前端单摄/双摄请求 payload、默认位置重置、选择已有 captures 目录和错误状态测试

## 9. 端到端与兼容验收

- [ ] 9.1 验证默认位置单摄：视频、事件、标记、时间线、manifest 和分析产物均可从同一会话目录读取
- [ ] 9.2 验证自定义移动硬盘位置单摄和双摄：重启应用后重新选择原目录不会产生重复 captures 或覆盖旧录制
- [x] 9.3 验证同一天多次录制均使用独立 capture_take_id 目录
- [ ] 9.4 验证拔出移动硬盘后录制立即失败、部分内容保留、SQLite 索引可查询且不触发分析
- [ ] 9.5 验证历史默认目录录制仍可查询、播放、分析和删除
- [x] 9.6 运行前端 build/test 与后端相关测试；lint 仍受仓库既有问题阻塞，原生 picker 需在本机人工点击验收
