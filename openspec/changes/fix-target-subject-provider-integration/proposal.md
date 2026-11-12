# Proposal

## Why

目标人物候选导出分支155fbb4相对main0ce572b具有独立科研价值，但合并评估已复现依赖接入、安装包缺契约、帧数不一致和跟踪配置不可追溯四项问题。负责人已在本次对话明确批准修复、回归测试及测试通过后合入main。

## What Changes

- 保留main的单一依赖源与哈希锁，整合既有独立CLI，不接入产品API或人物确认流程。
- 随wheel/sdist提供版本化契约数据，源码与安装包使用相同校验逻辑并验证数据镜像一致。
- 校验实际媒体尺寸、帧率与完整帧数；不一致时失败且不发布结果，不静默截断或补造缺失帧。
- 固定并显式选择跟踪算法，将有效配置纳入摘要，使环境变量不再暗改同一请求。
- 增加上述问题的回归与安装包测试；恢复现有CI的Python/runner兼容，保持全部门禁。

## Capabilities

### New Capabilities

- `target-subject-provider`：独立科研人物候选导出、输入完整性、契约分发及可复现配置。

### Modified Capabilities

无。既有automatic-player-roster-candidates面向产品人物确认，project-delivery-quality-gates已有依赖/隔离要求；本项不改变其规格或批准其余研究提案。

## Impact

仅影响新增provider、契约数据、后端依赖/安装配置、相关测试与CI runner。依赖安装仍从backend/pyproject.toml生成哈希锁，不改已有版本；用新隔离worktree工作，保留原5分支及3个worktree。实施、验证及测试通过后合并已获本次明确授权；OpenSpec归档、模型发布、部署及历史资料修改未授权。回滚为撤回本次集成提交，原研究分支及历史资产不变。

管理记录：[PB-024](https://app.notion.com/p/416f602574aa81c0ad4dcaacded93497)、[DEC-005本轮授权](https://app.notion.com/p/416f602574aa811e8a31c3f290dfcfab)、[集成验证文档](https://app.notion.com/p/416f602574aa816aacfccecb28a49531)。
