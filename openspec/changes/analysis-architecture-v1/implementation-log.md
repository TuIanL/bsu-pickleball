# 实施记录

## 2026-10-17：基线与合同

- 实施分支：codex/analysis-architecture-v1，起点为备份提交 0793a71（应用代码基线 2665bc3）。备份分支不修改。
- 活跃四人身份 change 尚有 1.2/1.3/6.2/6.3/6.5/7.6 未完成；本轮不编辑 global_state、joint 内部身份裁决或算法阈值。共享 Executor 的配置/engine 接入在当前基线上独立修改。
- 旧链路基线命令：backend/.venv/bin/python -m pytest tests/test_analysis_window.py tests/test_analysis_worker_liveness.py tests/test_analysis_run_trace_orchestration.py tests/test_multiview_orchestration.py -q（在 backend 目录）。结果：69 passed，218.60s。
- 基线覆盖窗口裁剪、Worker liveness/取消/中断、失败重试证据、多视角编排与执行体；本组未观察到既有失败。未将其作为算法质量或真实媒体验收。
- 轻量导入检查：新进程导入合同和 Registry，24 个能力条目；cv2、ultralytics、torch、mmpose 均未导入，非法 unavailable 节点状态被拒绝。
- 提交策略：默认请求继续 legacy_v1；模块提交仅显式 modular_v1，提供单独开关关闭新模块提交，保留 reader 和执行中的记录。Shot/Rally、指标、报告和 joint 内部协同均不迁移。

下列记录按实施阶段追加，任务进度以 tasks.md 为准。

## 合同、缓存和 Worker 集成

- tests/test_modular_analysis_runtime.py：17 passed（fixture 与集成，非真实模型）。覆盖稳定 hash、最小依赖、窗口传播/预算、缓存重建、并发发布、orphan、旧租约拒绝、间接血缘、控制信号、独立目标策略、失败阻断、同计划显式恢复、窄重算和 API/Planner 一致性。
- tests/test_modular_analysis_runtime.py + tests/test_analysis_run_trace.py + tests/test_analysis_window.py：47 passed。
- tests/test_modular_analysis_runtime.py + tests/test_api_smoke.py：59 passed。出现既有 Starlette/Pydantic 弃用及 diagnostics 序列化警告，未观察到用例失败。
- 模块返回清单，测试将 legacy pipeline_factory/on_completed 设置为禁止调用，全部模块测试通过。
- 同键损坏重建产生新 artifact_id；并发生产不覆盖内容；文件 finalize 后 DB 前故障留下不可命中的 orphan；共享引用与血缘保留上游。

## 最终实现及回归

- 纯合同/静态 Registry/Planner 与能力实现分目录；24 个能力中 3 个生产实现、21 个 planned，未来球拍/挥拍/动作/Shot/落点/语义/战术骨架有实际可导入 schema。
- 请求窗口、上下文预算、时间/采样、实际输入和消费字段冻结；校准的 metric 有效域、JSON 类型参数和 observation scope 另有行为测试。
- 沿用既有 SQLite 控制面、Worker/lease/CPU 资源限制，增加 immutable Artifact、cache CAS、血缘/source pin、attempt 和 ModularRunManifest；模块完成不调用产品报告回调。
- CLI/API 共用服务；只读 preview 不构造 JobStore/StorageService，不隐式 mkdir/schema。模块详情展示节点、缓存、部分清单和 trace，任务列表跳转不要求 reportId。
- RTMPose 输出本来就是像素，去掉二次缩放并验证 x=100/y=200；每帧 observation 隔离 visibility，不把人框顺序当稳定身份。原 detector/pose 算法阈值不调整。
- Legacy 单摄 Executor 修复持久化 enableModelInference/enablePoseInference 的保真传递；原 global_state/joint 身份裁决未改。
- 最终模块合同测试 30 passed；新增来源/参数/typed catalog/queued cancel 与 API new-version 之后的模块+删除+热路径+双摄+trace 回归 120 passed、2 warnings，3.96s。
- 全量后端 1805 passed、1 skipped、22 warnings，523.33s；前端相关 51 passed 后，全量前端 98 files/755 passed，55.98s；production build 退出 0。
- 真实模型首次在沙箱冷导入/字体缓存阶段长时间等待，两次隔离 smoke 被主动中断并保留 interrupted 证据，不计通过。配置可写模型缓存后完整 acceptance 跑通；最终五场景证据见 evidence/real-window-validation.json。
- ESLint 排除 `.runtime` 中 MPEG-TS 生成片段，并修正任务页原有 misplaced suppression；本期 TS 文件 0 errors/2 warnings。全仓仍有 3 errors/43 warnings，其中 3 个错误通过 git show 备份 HEAD 在未修改的 AnalysisRosterConfirmation/Modal 中复现，未将全仓 lint 标为通过。
- 完整命令、日志、14 spec 覆盖和四类证据见 validation.md；开发与扩展示例见 docs/analysis-architecture-v1.md。

## 真实推理与限制

来源为 take_sync_20260720_121319_e7f03b 的 174/175 两路既有视频，60–90s、stride=30，来源/PTS/模型资产强摘要均归档。输出在隔离 runtime 根，不改原媒体或生产任务。所有场景禁止完整 Pipeline/legacy 完成回调。

- 单摄球、人、姿态均真实执行，每节点 1 capture/1 model constructor/60 model executions；wall 204.916s，包含 RTMPose 冷启动。
- 同窗口新 Job 三节点全 cached，全部零 capture/模型，wall 10.313s；仅 pose confidence=0.45 时只姿态重算，wall 27.601s。
- 双摄 raw ball 只有一个节点，2 capture/1 model constructor/120 model executions，wall 27.001s；重复新 Job 全缓存，wall 20.077s。
- 全缓存仍强核验约 1GB/路媒体，不是零源 I/O。没有旧全链路同机对照，不报告提速倍数。
- 解码计数为应用层 read/grab，OpenCV 内部 GOP 预读不可见。节点间有界重解码，未承诺单遍共享流。
- quality 只验证证据结构、像素单位、主体作用域、时间/机位映射和可读性；没有人工标签精度，未来模型仍 planned。
- 模型 runtime_versions 身份增强发生在真实准备之后，归档明确将安装版本标为运行后记录，未篡改原冻结计划。

## 最终 OpenSpec 和工作区检查

- `openspec validate analysis-architecture-v1 --strict --json --no-interactive`：1/1 passed，0 failed。
- `openspec validate --all --strict --json --no-interactive`：207/207 passed，205 specs + 2 changes。
- 80/80 任务完成；完整产品迁移和 21 个 planned 能力模型保留为后续 change，不把算法精度评估算作本期已做。
- `openspec instructions apply` 返回 all_done（80 complete/0 remaining），status 的四类产物均 done。当前 reader 只读核验真实验收的 5 个冻结计划及 5 个不可变产物全部有效，未导入 cv2/torch/ultralytics/mmpose。
- `git diff --check`、全部改动/新增文本的末行换行与尾随空白、文档链接、真实复现输入路径均检查通过。
- 当前分支 codex/analysis-architecture-v1；备份仍为 0793a7163125490d12a1e1f6ea35b5dd9158ef90，main 仍为 2665bc3b974656cec45cd54e875d03cd3a8994c6。无 identity/joint 内部修改，生成 runtime/dist/model 数据未纳入版本改动；未 commit/push/archive。
