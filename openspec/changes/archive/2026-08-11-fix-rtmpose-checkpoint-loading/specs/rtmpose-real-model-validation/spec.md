## ADDED Requirements

### Requirement: Trusted RTMPose checkpoint loading compatibility

当 RTMPose 配置和 checkpoint 路径已经通过本地资产校验，且路径指向受信任的 OpenMMLab 模型时，适配器 SHALL 在调用 MMPose `init_model` 前建立与当前 PyTorch `weights_only` 默认值兼容的加载上下文。该兼容保障 MUST 由 RTMPose 运行时自身提供，不得只依赖启动脚本或调用方环境变量。

#### Scenario: Direct backend launch loads the supported checkpoint

- **WHEN** 后端通过直接 Uvicorn 命令启动，RTMPose 依赖已安装，且 Body8-Halpe26 config/checkpoint 路径可读
- **THEN** `RTMPose26Adapter` SHALL 成功初始化模型，不得因为 `numpy.ndarray` safe-global 或 `weights_only` 默认值错误而跳过姿态阶段

#### Scenario: Trusted checkpoint loads with the compatibility environment absent

- **WHEN** 进程启动前未设置 `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD`
- **AND** 适配器收到仓库配置的受信任 checkpoint
- **THEN** 适配器 SHALL 在模型初始化前设置或等价地应用兼容策略，并继续执行 `inference_topdown`

#### Scenario: Missing pose runtime remains degraded and explicit

- **WHEN** MMPose 依赖、config 或 checkpoint 不存在
- **THEN** 适配器或 pipeline SHALL 保持现有不可用/跳过行为，并 SHALL NOT 创建看似成功的骨架 artifact

### Requirement: Single-frame validation covers checkpoint compatibility

现有单帧 RTMPose 验证路径 SHALL 在不预设外部 `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD` 的情况下覆盖真实 checkpoint 初始化和推理。

#### Scenario: Validation succeeds without external compatibility setup

- **WHEN** 使用仓库 Body8-Halpe26 config/checkpoint、backend 虚拟环境、一个有效帧和人体框运行验证脚本
- **THEN** 验证 SHALL 返回成功，并输出至少一个包含 26 个关键点的 `PoseOverlayFrame`

#### Scenario: Validation failure identifies the real prerequisite

- **WHEN** 依赖、模型资产、设备或推理步骤仍然不可用
- **THEN** 验证 SHALL 以非零状态退出，并报告具体失败阶段，而不是将模型加载错误伪装成空骨架结果
