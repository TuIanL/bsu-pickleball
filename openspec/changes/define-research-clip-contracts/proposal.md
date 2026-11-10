# Proposal

## Why

现有分析上下文已区分媒体、主体和坐标，但研究片段尚缺一个明确绑定人工确认、三种时间地址、质量与修订来源的兼容快照。旧采集规范可能过时，其标签、COCO17和含式帧边界不能直接替代当前代码及版本化数据合同。

## What Changes

- 为人工确认的研究片段定义版本化Context快照及输入/输出Schema，复用现有video、clip、roster、calibration与artifact身份。
- 对齐源帧号、真实PTS、take统一时间，显式转换包含式源帧区间与半开执行窗口，保留实际初始化上下文。
- 分开Session匿名人员、P槽位、view-local track/epoch和global映射；分开身份观测与空间指标资格。
- 为人工确认/修订、执行状态、证据可用性、完整性和研究质量profile建立独立字段与兼容适配fixtures。
- 对旧taxonomy和COCO17/Halpe26仅登记版本与冲突，不重标、不重训、不统一覆盖。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `analysis-context-contract`：增加研究片段快照、帧区间导入、人工确认与质量profile引用的要求；采用ADDED增量，保留现有五项要求及场景。

## Impact

- 前置：`establish-research-evidence-baseline`的资产身份合同稳定并在实施前具备可用参考包。可先评审本文，但不绕过输入条件宣称验收。
- 拟影响新增研究Context/Pydantic合同、Schema文档与只读legacy/modular适配测试；不在本项接入页面、运行模型或执行真实数据库迁移。
- 输入为可核验的资产引用及现有请求；输出为可校验的研究快照、时间/主体/单位映射说明和失败fixtures。
- 对应Notion PB-007/008/009；API仍兼容`AnalysisJobCreate`现有字段。具体提交profile在后续工作流Change实现。
- 管理入口：[提案索引](https://app.notion.com/p/414f602574aa81a2bd37dd819f9833bf)、[PB-008 实施任务](https://app.notion.com/p/414f602574aa81eeba90fe3bab0dfe73?pvs=204)；Notion维护状态，本目录保存规格和验证依据。
- 风险是VFR边界、旧标签信息不足、坐标朝向和错误主体映射；信息不足时显式拒绝或保留unknown，不补造值。
- 回滚为禁用研究合同适配，保留原始快照及版本读取；不改变旧请求、原标注与旧产物。当前待Review，不包含Apply授权。
