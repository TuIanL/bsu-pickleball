## Context

当前 `RTMPose26Adapter` 在调用 MMPose `init_model` 前只加入了一个 NumPy 反序列化函数的 safe global。PyTorch 2.6 及之后的默认 `weights_only=True` 仍会拒绝该项目使用的 OpenMMLab checkpoint 中的 `numpy.ndarray`，因此直接启动后端时，RTMPose 第一次推理会失败，单摄子任务将姿态阶段标记为 skipped，双摄 Parent 只能继承没有骨架的 child 产物。

仓库已经提供 `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` 启动约定，并且模型权重位于受信任的仓库本地 `models/rtmpose/` 路径。本次修复需要覆盖直接运行 Uvicorn、测试脚本和启动脚本三种入口，同时保持没有 MMPose 或模型资产时后端仍可启动。

## Goals / Non-Goals

**Goals:**

- 使配置路径可解析的受信任 RTMPose checkpoint 在当前 PyTorch/MMEngine 组合下完成模型初始化。
- 让适配器不依赖调用方是否提前设置 `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD`。
- 保持 MMPose、模型文件和 CUDA 仍为可选依赖；缺失时继续返回清晰的不可用信息。
- 用单帧真实模型验证证明权重加载和 `inference_topdown` 均可用。
- 确保双摄 Parent 携带参考机位的真实输入元数据，避免真实 child 被前端展示为 demo 任务。

**Non-Goals:**

- 不下载、提交或替换模型权重。
- 不把任意用户输入路径视为可信 checkpoint。
- 不修改 YOLO、双摄融合、任务报告或历史任务产物。

## Decisions

### 1. 在 RTMPose 适配器内建立兼容保障

在 `RTMPose26Adapter._load_model()` 的 `init_model` 调用前设置 PyTorch 官方支持的 `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` 兼容开关，并继续注册 `numpy.ndarray` 与相关 NumPy 反序列化对象。这样直接运行后端时也覆盖到真实模型加载路径，启动脚本中的同名变量作为外层保障继续保留。

不通过手工读取 checkpoint 再拼装 MMPose 模型，因为这会重复 `init_model` 的配置解析和权重映射逻辑，且容易与 MMPose 版本耦合。

### 2. 将 checkpoint 信任边界限定为本地配置资产

该兼容模式只在 RTMPose 适配器加载 `config_path`/`checkpoint_path` 时使用。两者必须先通过现有路径存在性检查；路径来源是环境配置或仓库模型目录，不由视频上传请求提供。验证脚本和文档明确该模式只适用于用户信任的 OpenMMLab 权重。

### 3. 用真实单帧验证锁定回归

保留现有 `validate_rtmpose.py` 作为验证入口，增加适配器级测试覆盖兼容准备逻辑；实现后使用仓库实际 Body8-Halpe26 config/checkpoint 运行一次单帧验证。完整视频任务不作为单元测试，避免基础测试被 CPU 模型耗时和本地资产绑定。

## Risks / Trade-offs

- [强制关闭 weights-only 会扩大 checkpoint 反序列化能力] → 只对配置的本地 RTMPose checkpoint 使用，并在代码注释、README 和验证输出中明确“仅限信任来源”。
- [未来 checkpoint 需要额外 NumPy 类型] → 保留 `weights_only` 错误作为诊断信息，并让单帧验证在模型初始化阶段直接失败，不生成伪造骨架 artifact。
- [CPU 全视频 RTMPose 仍然较慢] → 保持现有抽帧步长和设备配置，不在本次变更扩大推理范围。

## Migration Plan

1. 更新适配器和测试/文档。
2. 在当前 `backend/.venv` 中运行 check-only 与真实单帧验证。
3. 重新启动后端后重新创建或重试需要骨架的分析任务；历史任务不会自动补生成 `pose_overlay.json`。
4. 若验证失败，保留现有姿态降级路径并根据验证错误回滚适配器改动。

## Open Questions

- 是否将 `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD` 后续替换为升级 MMEngine 后的显式 `weights_only=False` API，需要结合未来依赖版本再决定；本次先使用当前运行环境已验证的兼容方式。
