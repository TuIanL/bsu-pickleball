## 1. 编排契约与任务状态

- [x] 1.1 对照现有 `multiview-progress-state-machine` 的阶段定义，确认 `multiview-ball-analysis` 的唯一状态字段、状态迁移和未完成任务的兼容读取规则
- [x] 1.2 在 joint 阶段图中加入双摄球分析阶段，并让 metrics、visualization、report 依赖该阶段的终态
- [x] 1.3 为球分析阶段接入 Parent 的取消、重试、删除级联和应用启动 reconciliation
- [x] 1.4 为球分析阶段增加超时、异常捕获和 degraded/failed 状态 detail，验证球员结果不因球分析失败而丢失
- [x] 1.5 将最终 `result.json` 写入和 completed 事件移动到球相关 artifacts 发布与校验之后

## 2. Canonical 双摄球处理链路

- [x] 2.1 在 joint 执行上下文中构造并传递 `CanonicalAnalysisClock` 与 `SynchronizedFrameBundle`
- [x] 2.2 将实际解码、frame index、timestamp 和 `frame_stride` 统一为真实读取语义，补齐 stride 大于 1 的回归测试
- [x] 2.3 统一 observation、association、tracker 和 triangulation 的内部时间单位为秒，并在 evidence/API 边界明确毫秒字段
- [x] 2.4 将双摄球处理拆为 decode bundle、detect/filter、candidate snapshot、association、tracker、stereo evidence 六个可测试步骤
- [x] 2.5 确保每个视角每个 canonical tick 只运行一次 detector，并让 tracker 与 stereo 共享同一候选快照
- [x] 2.6 只允许 available frame 进入权威 stereo measurement，记录缺帧、外推帧和拒配对原因
- [x] 2.7 实现带阈值的双摄时间配对，保留两路真实 timestamp、frame index、tick_id 和时间差
- [x] 2.8 保留离线 `real_data_runner` 作为 debug/regression 入口，但显式标记 offline context，禁止其绕过 Parent 正式发布

## 3. 重建正确性与质量门

- [x] 3.1 修复 triangulation 选择最佳 Cam2 观测后返回循环末值的问题，并增加多候选回归用例
- [x] 3.2 修复 spline knot、参数端点和 `t=1` 的基函数边界行为，增加首点、末点和单段轨迹测试
- [x] 3.3 校验相机尺寸、坐标单位、深度范围和射线夹角，防止错误标定或单位进入三维轨迹
- [x] 3.4 修正速度计算与 `km/h` 序列化，增加 ft/s、m/s、km/h 的转换测试
- [x] 3.5 为 stereo measurement 记录三角测量角度、重投影误差、深度/空间范围检查和质量等级
- [x] 3.6 实现 `FULL_ESTIMATED_3D`、`PARTIAL_3D`、`LANDING_ONLY`、`UNAVAILABLE` 的确定性状态判定
- [x] 3.7 让无效三维点在轨迹中断开或带显式 validity，不允许低质量点无标记连接为完整球路

## 4. Artifact 与 Composer 发布

- [x] 4.1 扩展 `AnalysisArtifacts`，增加 reconstructed ball trajectory 和 stereo evidence 的 path、URL、status、detail 字段
- [x] 4.2 在 Composer 中从球分析阶段接收两个产物，并生成 Parent 级 `reconstructed_ball_trajectory.v3` 引用
- [x] 4.3 在 Composer 中发布不可变 `multiview_ball_stereo_evidence.v1`，保留 schema、完整性信息和输入窗口关联
- [x] 4.4 增加 Composer 对时间单位、速度单位、质量字段和 overall status 的一致性校验
- [x] 4.5 将球分析失败、超时、不可用和部分可用状态映射为稳定的 artifact status/detail
- [x] 4.6 确认 artifact API 仅允许合法 task scope 下的两个球产物名称，并补充路径穿越/越权测试
- [x] 4.7 验证最终 Parent result、artifact URL 和完成事件之间不存在先后竞态

## 5. 前端球路展示链路

- [x] 5.1 扩展 `analysisClient` 从 Parent artifacts 读取 v3 轨迹、stereo evidence、status 和 detail，并保持 legacy fallback
- [x] 5.2 在 `BallTrajectoryPage` 中增加 v3 schema 识别、三维/俯视球场轨迹、落点、事件和质量指标渲染
- [x] 5.3 为 `PARTIAL_3D`、`LANDING_ONLY`、`UNAVAILABLE` 和运行中状态实现明确空态、降级态和无效段视觉语义
- [x] 5.4 保证旧任务的 legacy/v1/v2 轨迹仍可读取，新任务同时存在多版本时默认选择 v3 并标明版本差异
- [x] 5.5 在 `VisionPage` 展示双摄球分析状态、摘要和球路页面入口；没有 world-to-pixel 标定时禁止直接视频像素叠加
- [x] 5.6 增加前端契约测试，覆盖 URL 缺失但 status 存在、artifact 读取失败、旧任务和 v3 降级状态

## 6. 测试与真实数据验收

- [x] 6.1 补充 canonical tick、stride、秒/毫秒、时间门和 available-frame 规则的单元测试
- [x] 6.2 补充候选只检测一次、候选共享、最佳观测选择、spline endpoint 和速度单位的回归测试
- [x] 6.3 补充 Composer、artifact API 与 Parent 完成时序的集成测试
- [x] 6.4 补充 joint 任务球分析成功、部分三维、仅落点、失败和超时的端到端测试
- [ ] 6.5 使用可授权的真实双摄样例验证 evidence 条数、配对覆盖率、重投影误差、落点和页面展示
- [x] 6.6 将现有球 stereo、artifact、consumer 测试与新增测试一起运行，确认旧版轨迹兼容性
- [x] 6.7 记录真实数据验收报告中的输入窗口、标定版本、模型版本、阈值、状态和已知限制
