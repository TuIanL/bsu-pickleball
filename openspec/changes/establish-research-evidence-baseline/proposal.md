# Proposal

## Why

科研复盘首版已确定采用人工确认、已标定的真实比赛片段，但代码、源媒体、模型和历史Job证据分散在main、未合并功能线、外接盘及Windows机器。目录可见或软件测试通过不足以证明真实输入、版本和验收结果能够对应，需先建立可核验的科研证据包。

## What Changes

- 增加科研资产Manifest及只读核验入口，关联源视频、PTS、同步、标定、名册、模型、运行结果与人工记录。
- 明确real、fixture与unknown，区分位置不可达、缺文件、摘要不符和未核验；不把本地合成上传夹具当作正式素材。
- 分别登记main `99c0f19`、功能线 `43b5727`、运行时commit及dirty patch摘要，保留原始pass/fail、范围和复核来源。
- 导出轻量可移植索引和核验报告；原始视频、模型、数据库及历史结果不搬移、不覆盖，不执行推理。

## Capabilities

### New Capabilities

- `research-evidence-package`：科研复盘所需的跨媒体、模型、人工复核及运行证据的可移植索引与只读校验。

### Modified Capabilities

无。复用`analysis-artifact-lineage`的不可变产物与可用性概念，不重建其运行时缓存和访问服务。

## Impact

- 拟影响独立核验脚本、科研Manifest Schema、已有StorageService/来源摘要的只读适配及对应测试；不新增公共任意路径API或数据库迁移。
- 输入为明确授权的资产根和固定版本记录；输出为新目录中的Manifest、内容摘要、缺失清单与核验日志。真实资产路径只保存在本地位置映射。
- 前置为产品边界已确认、源资产可读取；最新Windows原始Job尚缺时允许生成partial索引，但不得标为完整验收。
- 对应Notion PB-003/004/005/006/020。提案与实施任务分开；当前仅Propose，Review、Apply、Verify、Archive分别授权。
- 管理入口：[提案索引](https://app.notion.com/p/414f602574aa81a2bd37dd819f9833bf)、[PB-006 实施任务](https://app.notion.com/p/414f602574aa8177b422f65603258927?pvs=204)；Notion维护状态，本目录保存规格和验证依据。
- 风险是大文件I/O、历史结果签名未含代码/同步内容及来源不明；采用分块核验、显式unknown和独立版本字段。回滚为停用新工具并保留其索引，不触碰旧资产。
