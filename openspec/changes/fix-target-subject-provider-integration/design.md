# Design

## Context

见proposal.md。main0ce572b已有锁定依赖和新跟踪器；155fbb4仅增加独立provider，依赖清单冲突。临时评估14个新增测试及10个跟踪测试通过，另复现wheel缺契约、三帧输入的错误范围及环境变量改变候选数。

## Goals / Non-Goals

**Goals:** 兼容旧请求；固定工具行为；验证真实分发与干净安装；保持现有分支和原始资产不变。

**Non-Goals:** 不接入Web/API、不修改双摄或四人全段质量门槛、不重训模型、不更改外部动作数据仓库，不归档本Change或其他Change。

## Decisions

1. 在新隔离worktree从main建立集成分支，合入原provider提交后修复，保留原提交可追溯性。requirements.txt保留main的锁文件入口；新增jsonschema和分发测试依赖只在pyproject声明，按旧版本约束补充哈希锁。
2. 公开backend/contracts/target_subject/v1保持兼容；将同一JSON集合随app包作为contract_data/v1分发，运行时用importlib.resources加载。内容镜像与摘要一致性测试防止漂移。相比自定义构建后端，多一份受校验的数据镜像更直接且适配Windows。
3. 新增可选tracker_algorithm（motion/legacy）；省略时显式固定motion，不读取全局算法变量。preflight与执行共用有效配置解析，configuration_sha256包含补齐默认值的配置；不改变现有result Schema字段，不影响旧读取端。
4. 完整解码时核验宽高与fps（相对容差0.001、绝对容差0.01，仅用于元数据浮点误差）。实际帧数多/少均拒绝；内存构造器拒绝越界/重复帧号。失败不写结果，已有结果不覆盖。本工具仍仅支持CFR研究片段，不替代PTS/双摄时钟合同。
5. 在开发依赖中声明build/setuptools/wheel，测试在临时目录构建sdist、再离线构建wheel并隔离校验，禁止从源码路径偷取契约。CI只将Python任务的runner固定到提供既有Python的版本，不跳过门禁、不提高算法阈值。

## Risks / Trade-offs

- 数据镜像漂移：完整文件集合及摘要双向校验；契约更新必须同步并更新清单。
- 大视频解码成本：保留现有受控片段工具范围；本次不宣称支持全片或VFR。
- 现有CI/历史测试问题：区分原有基线与本项回归，不能删测试或伪造绿色结果；记录实际运行证据。
- 干净基础回归额外暴露非Windows测试缺少psutil及Windows flag替身、取消录制测试的立即退出竞争：只补开发依赖和测试同步，保持原断言及生产脚本不变；完整复跑验证。

## Migration Plan

先完成依赖、分发、输入与配置回归，再执行现有基础套件和CI。测试通过后按本轮明确授权通过PR合入main，并只推进main本地引用；不切换/重置三个既有worktree，不修改其他分支。回滚用revert本次集成；保留原provider分支和原始产物。OpenSpec主规格同步和Archive需另行授权。
