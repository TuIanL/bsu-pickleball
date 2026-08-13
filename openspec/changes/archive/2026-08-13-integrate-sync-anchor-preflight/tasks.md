## 1. 同步锚点领域模型与共享拟合

- [x] 1.1 定义同步锚点状态、草稿、确认请求/响应、质量摘要、provenance 和结构化校验问题的后端 schema，并补充前端对应类型
- [x] 1.2 将 CLI 中的 anchors payload 校验、线性拟合和 `dual_camera_sync_calibration.v1` 组装提取为可被 API 与脚本共同调用的服务函数
- [x] 1.3 更新 `calibrate_dual_camera_sync.py` 使用共享拟合服务，并增加输出兼容性回归测试
- [x] 1.4 实现当前双摄素材 provenance 采集与稳定指纹，覆盖 camera、registered video、timing sidecar、frame count 和 PTS 范围

## 2. CaptureTake 级资产服务

- [x] 2.1 实现 CaptureTake 时间线目录中的草稿、原始 anchors、confirmation metadata 和 calibration 路径及原子读写
- [x] 2.2 实现带 optimistic revision 的草稿读取与保存，并对过期 revision 返回冲突结果
- [x] 2.3 实现确认事务：验证素材身份与锚点、拟合、生成质量摘要并发布同一 revision 的人工确认资产
- [x] 2.4 实现 `not_required`、`required`、`draft`、`confirmed`、`auto_degraded`、`invalidated` 状态解析及 `analysis_allowed/reason_codes` 策略输出
- [x] 2.5 实现 provenance 变化失效判定，确保 AnalysisJob、clip window 和算法配置变化不会使确认失效
- [x] 2.6 实现历史 `manual_anchors` 与现有 `auto_degraded_from_recording_timing` 文件的兼容识别和安全懒迁移

## 3. API 与分析前置门禁

- [x] 3.1 增加 CaptureTake 同步锚点状态、草稿读取/保存、确认和导出 API，并统一错误响应格式
- [x] 3.2 在 CaptureTake 轻量详情或专用状态响应中暴露当前状态、revision、来源、质量摘要和失效原因
- [x] 3.3 将同步锚点策略接入 multiview 创建任务 preflight，在创建 Parent/child 前重新校验且失败时不产生部分任务
- [x] 3.4 调整自动 degraded calibration 恢复逻辑，保证其不会覆盖有效人工确认或被表述为人工确认
- [x] 3.5 增加 API 和服务测试，覆盖有效确认、无效锚点、revision 冲突、自动降级、无需标注、失效和跨分析复用

## 4. 内置同步锚点工作台闭环

- [x] 4.1 在 `analysisClient` 增加同步锚点状态、草稿、确认和导出调用，并使用服务端 schema 类型
- [x] 4.2 将工作台初始化改为读取服务端草稿与状态，保留旧 localStorage 草稿的一次性显式导入
- [x] 4.3 将锚点编辑接入后端草稿保存与 revision 冲突处理，支持离开页面后跨浏览器会话继续
- [x] 4.4 用“提交并确认”替换下载文件主流程，展示服务端 coverage、residual 和结构化校验问题；JSON 下载降为诊断操作
- [x] 4.5 确认成功后返回同一 CaptureTake 的双摄分析向导，并确保直接打开、刷新和错误重试均有正确返回路径
- [x] 4.6 增加工作台交互测试，覆盖草稿恢复、旧草稿导入、保存冲突、确认成功、确认失败和导出不改变状态

## 5. 双摄分析向导状态与门禁

- [x] 5.1 在素材检查阶段加载录制级同步锚点状态，分别呈现无需标注、需要标注、草稿、人工确认、自动估算和已失效状态
- [x] 5.2 按服务端 `analysis_allowed` 控制进入 A 机位标定的按钮，并为阻塞状态提供开始/继续/重新标注操作
- [x] 5.3 展示 confirmed calibration 的锚点数、覆盖率、残差、确认时间和来源，确保自动估算不显示为人工确认
- [x] 5.4 从工作台返回后重新加载状态并恢复安全的向导上下文，避免重复完成已确认锚点
- [x] 5.5 处理创建任务时状态变更的结构化 preflight 错误，将用户带回素材与同步检查且不丢失双机位标定草稿
- [x] 5.6 更新向导测试，覆盖全部状态渲染、按钮门禁、工作台往返、跨分析复用和服务端二次校验失败

## 6. 集成验证与文档

- [x] 6.1 增加端到端后端测试：双摄 CaptureTake 保存草稿、确认、创建两次 AnalysisJob 并复用同一 calibration revision
- [x] 6.2 增加素材或 timing sidecar 替换后的失效集成测试，并验证旧 revision 保留但不再用于当前 preflight
- [x] 6.3 运行相关前后端测试、类型检查和 lint，修复回归并记录实际验证命令
- [x] 6.4 更新双摄同步与分析流程文档，说明状态语义、内置工作台、自动降级区别、复用和失效条件
