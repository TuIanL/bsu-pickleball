## 1. Field Session 配置与兼容

- [x] 1.1 为 Field Session ORM 增加 `display_mode` 字段、`standard/showcase` 枚举和数据库迁移，历史记录默认读取为 `standard`
- [x] 1.2 扩展 Field Session 创建、更新、列表和详情 schema/API，校验 `showcase` 只能与 `camera_setup=dual` 组合
- [x] 1.3 将 `display_mode` 加入前端 FieldSession、创建请求和详情类型，并覆盖历史响应缺失字段的兼容默认值
- [x] 1.4 锁定 `live` 任务的 `display_mode` 与 `camera_setup`，并在 CaptureTake/录制会话中保存本次配置快照
- [x] 1.5 为展示模式创建、标准模式默认值、非法组合和 live 状态锁定补充后端 schema/service/API 测试

## 2. ShowcaseRuntime 实时旁路

- [x] 2.1 定义 ShowcaseRuntime、机位运行状态、展示流订阅和停止结果的数据模型，区分 recording 与 overlay 状态
- [x] 2.2 实现按 CaptureTake 管理的 ShowcaseRuntime 生命周期、会话注册、状态读取、幂等停止和资源回收
- [x] 2.3 实现每个机位独立的摄像头 reader 和 bounded latest-frame queue，丢弃过期帧并防止推理积压
- [x] 2.4 实现轻量人体推理 worker，复用 YOLO person detector、MultiObjectTracker 和现有 overlay 绘制数据，输出 bbox、track ID 和置信度
- [x] 2.5 实现展示推理配置，包括处理分辨率、目标推理 FPS、JPEG 质量和实际 FPS/延迟统计，不能用目标值冒充实测值
- [x] 2.6 实现可选球检测分支，复用 BallTracker 输出 image-space 球点和固定长度短轨迹，并在模型不可用或无有效候选时返回明确状态
- [x] 2.7 实现展示运行状态接口，返回 CaptureTake、机位连接、最近帧、实际推理 FPS、track 数量、球状态和降级原因
- [x] 2.8 实现按 ShowcaseRuntime 和 camera slot 绑定的带叠加 MJPEG 展示流，普通 `/api/cameras/{camera_id}/preview` 保持原实现
- [x] 2.9 为流客户端断开、重复订阅、机位断流、模型加载失败、停止超时和重复停止补充后端单元测试

## 3. 双摄录制生命周期接线

- [x] 3.1 在双摄录制成功启动后，根据 Field Session 快照决定是否启动 ShowcaseRuntime，并将展示运行引用加入运行状态响应
- [x] 3.2 保证标准模式完全不创建展示 worker、不加载展示模型、不增加展示专用摄像头连接，并添加回归测试
- [x] 3.3 将展示旁路接入正常停止、取消、录制异常和进程恢复流程，确保旁路停止不会阻断 FFmpeg 原始录制收尾
- [x] 3.4 验证展示旁路异常只更新展示状态，不改变原始 TS 分段、CaptureTake 状态、双摄合并和正式分析入口
- [x] 3.5 为展示模式保存/恢复、旁路启动失败、单路断流和停止超时补充双摄录制集成测试

## 4. 前端配置与展示屏

- [x] 4.1 在 CaptureWizardPage 增加普通/展示模式选择，选择展示模式时强制双摄并在提交前显示配置状态
- [x] 4.2 在 CaptureHomePage、CaptureConsolePage 和相关任务卡片中回显 `display_mode`，标准任务保持现有操作和文案
- [x] 4.3 将展示运行引用、状态轮询和展示流 URL 接入采集控制台，提供打开独立展示屏的操作
- [x] 4.4 新增独立展示屏路由，按 cam_1/cam_2 全屏展示带叠加预览、录制状态、实时 FPS 和降级状态
- [x] 4.5 实现展示屏在展示流失效、人体模型不可用、球检测不可用和录制结束时的可解释状态与普通预览回退
- [x] 4.6 确保展示屏关闭、刷新或断开不会触发停止录制；任务切换时清理旧 ShowcaseRuntime 流引用
- [x] 4.7 为模式选择、双摄约束、标准模式回归、展示屏打开和异常状态展示补充前端测试

## 5. 录制后正式分析保持不变

- [x] 5.1 验证展示模式停止后仍按现有流程完成原始双摄分段收尾、CaptureTake 持久化和后续合并
- [x] 5.2 验证完整分析任务只读取原始录制产物，不读取实时叠加 JPEG 或 ShowcaseRuntime 临时状态
- [x] 5.3 验证现有双摄分析、报告、球路后处理和训练指导回归测试不受 `display_mode` 影响

## 6. 性能、设备验收与文档

- [x] 6.1 使用虚拟摄像头或固定视频完成双路人体框展示冒烟测试，记录实际推理 FPS、展示 FPS 和端到端延迟
- [ ] 6.2 在目标比赛电脑和真实双摄设备上压测至少 10 分钟，验证录制文件完整、展示延迟不持续增长且资源可回收
- [x] 6.3 分别验证人体模型可用、人体模型不可用、球模型可用和球模型不可用时的展示降级行为
- [ ] 6.4 基于真实体验者视频验收两路框归属、track 稳定性、机位隔离和停止后正式报告生成
- [x] 6.5 根据压测结果确定默认处理分辨率、推理 FPS、球检测默认开关和现场运行配置
- [x] 6.6 更新用户和现场操作文档，说明标准/展示模式差异、展示屏启动方式、球轨迹可用性和故障回退流程
