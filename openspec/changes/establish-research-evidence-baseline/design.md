# Design

## Context

动机见proposal.md。现有`analysis_runtime/sources.py`核验运行时媒体/模型身份，`StorageService`管理产品位置，`analysis-artifact-lineage`管理不可变产物。本项补充跨科研数据、历史Job与外部资料的导出索引，不另造缓存、任务系统或数据库。

11月10日外接盘恢复挂载；7个take目录可见，174源视频元数据探测成功，175探测15秒超时。两份旧Job质量JSON可读；最新Windows的`job-0d8ec77a76`与`job-2b677c38af`不在当前外接盘该take/analysis目录。存在性、元数据、内容摘要及全解码需分别记录。

本项涉及存储、模型、Job与数据来源的边界和大文件核验，因此编写design，不跳过规格。

## Goals / Non-Goals

**Goals:** 输出版本化、可验证的科研资产索引；将当前可核验与缺失证据分开；保持历史结论及原文件不变。

**Non-Goals:** 不搬迁资料、不复制整盘、不重编码、不加载权重、不运行模型、不改数据库、不发布数据；不以修复访问问题为由重建离线源目录。

## Decisions

### D1 采用内容身份加位置映射

建议新增`research_evidence_manifest.v1`合同。包含package_id、schema_version、基线、assets、run_refs、checks及limitations。asset含asset_id、kind、usage_kind、content_sha256或明确unknown、size、provenance和verification_status。run_ref引用所消费媒体/模型/上下文、code_revision、dirty_patch_sha256或未知、实际范围和原质量结果。

可分享Manifest使用逻辑locator；`locations.local.json`保存授权根与本机路径，不随分享包导出。路径不是ID。替代方案是直接复制原目录，可快速阅读但体积和个人路径不可移植，故不采用。

### D2 复用已核验记录并提供受限CLI

拟增加独立`backend/scripts/research_evidence.py`，提供build与verify；输入为明确的索引配置和授权来源根，输出为新目录中的manifest.json、checks.json及本地位置映射。复用现有摘要/存储只读适配，不导入应用lifespan、不初始化数据库或模型。不新增接受任意路径的HTTP入口。

原生Job与旧JSON通过只读导入适配，历史缺字段标unknown，不取当前HEAD补历史运行版本。分块流式计算摘要，可取消、限制媒体探测时间；记录检查实际范围。JSON结构校验使用现有依赖，不引入数据平台。

### D3 类型、完整性与算法质量正交

usage_kind由明确来源及检查依据表达real/fixture/unknown；工具不得仅凭扩展名自动认证real。availability与verification_status分离，原有algorithm verdict及范围照录。只有所选用途必需资产全部核验，才能标package completeness=complete；否则partial。完整索引也不表示模型质量通过。

## Risks / Trade-offs

- 大视频I/O和外接盘时延 → 分块、超时、取消、核验范围日志；不承诺固定耗时。
- 旧Job签名未含代码/同步 → 补充独立字段和证据等级，不回改旧签名。
- 来源/许可不明 → 保留unknown与待核实项，不把无记录解释为可公开。
- 工作区dirty → 保存patch摘要和基线；不自动stash、提交、重置或合并。

## Migration Plan

批准后先在隔离输出根验证fixtures，再只读索引明确授权的参考take。完整原始产物仍缺时交付partial包并记录PB-004阻塞。源输入前后摘要/修改时间检查作为不变性证据；不修改原数据库或默认运行根。

回滚只需停止使用新CLI和索引；保留已生成包用于追溯，不删除来源。后续契约Change消费本Manifest，不要求先合并功能分支。

## Review Gates

本提案范围对应PB-003/004/005/006/020。首次Apply前须批准本项和授权来源根；真实资料复制、模型发布、生产操作、归档或Git合并分别批准。当前全部实施任务未开始。
