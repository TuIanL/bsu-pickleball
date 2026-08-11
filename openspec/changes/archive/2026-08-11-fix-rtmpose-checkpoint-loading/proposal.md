## Why

真实双摄分析任务已将 RTMPose 标记为启用，但后端直接启动时没有继承 PyTorch 对受信任 OpenMMLab checkpoint 的反序列化兼容设置，导致两路子任务在首次加载权重时因 `numpy.ndarray` allowlist 错误被跳过。模型资产和依赖本身可用，因此需要把兼容性固化在 RTMPose 运行时中，避免分析结果缺失骨架。

## What Changes

- 让 `RTMPose26Adapter` 在加载受信任的本地 checkpoint 时显式处理 PyTorch `weights_only` 兼容问题，不依赖调用方是否通过启动脚本设置环境变量。
- 保留轻量后端的可选依赖边界；未安装 MMPose 或缺少模型资产时继续返回明确的不可用状态。
- 扩展 RTMPose 单帧验证，覆盖当前 checkpoint 的真实加载路径和兼容设置。
- 补充启动与模型说明，明确受信任本地权重的加载策略和安全边界。
- 不修改历史任务产物；修复后需要重新运行受影响的子任务才能生成骨架 artifact。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `rtmpose-real-model-validation`: 受信任且路径可解析的 RTMPose checkpoint 必须在当前支持的 PyTorch 运行时中完成初始化和单帧推理；只有依赖、资产或推理本身不可用时才进入降级状态。

## Impact

- 后端 RTMPose 适配器：`backend/app/vision/pose/rtmpose26_adapter.py`。
- RTMPose 验证脚本、单元测试和运行文档。
- 不改变分析 API、任务数据结构、双摄融合算法或已生成的历史结果。
