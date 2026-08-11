## 1. RTMPose 加载兼容

- [x] 1.1 在 `RTMPose26Adapter` 的模型初始化路径中固化受信任本地 checkpoint 的 PyTorch `weights_only` 兼容策略，并补齐 `numpy.ndarray` 相关 safe globals。
- [x] 1.2 保持依赖缺失、配置缺失和权重缺失时的现有可解释降级行为，避免生成伪造骨架 artifact。

## 2. 回归验证与文档

- [x] 2.1 增加适配器单元测试，验证未预设外部兼容环境变量时会准备模型加载兼容策略，并在测试后恢复环境状态。
- [x] 2.2 更新 RTMPose 验证脚本或 README，明确直接启动和启动脚本两种入口都使用受信任 checkpoint 加载策略。
- [x] 2.3 运行 RTMPose focused tests、check-only 验证和真实 Body8-Halpe26 单帧推理，确认输出 26 个关键点。
- [x] 2.4 运行 OpenSpec 校验并检查工作区 diff，确认不改动历史任务产物和无关导航变更。
- [x] 2.5 修正双摄 Parent 的真实输入元数据与推理开关透传，并用短窗口双摄任务验证两个 child 均成功生成骨架。
