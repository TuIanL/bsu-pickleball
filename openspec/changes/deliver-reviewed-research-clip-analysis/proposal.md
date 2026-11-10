# Proposal

## Why

已有工程能运行视频分析，最新功能线也有整段人物、姿态和二维球产物，但严格身份质量仍失败，研究人员无法把“运行成功”直接当作可用研究结果。首版需要围绕人工确认的片段形成输入核验、真实分析、复核及证据导出的有限闭环。

## What Changes

- 在既有分析入口增加显式选择的`research_clip_v1`研究profile，复用人工名册、标定、同步、窗口和现有Worker，不改默认分析行为。
- 必需结果限定为已确认主体的位置证据、描述性空间/移动指标、同步回放及研究证据包；姿态与球等能力独立可选。
- 对缺少必需输入、质量profile未批准、缺失观测、低覆盖及推理失败给明确状态，不回退demo、预测框或匿名编号替代个人结果。
- 复核记录采用追加修订，导出引用相同源帧/Job/代码/模型/合同与人工来源，复算产生新版本。

## Capabilities

### New Capabilities

- `research-clip-review-workflow`：研究片段的人工确认、受控分析、复核和证据导出流程。

### Modified Capabilities

无。研究profile消费已有`analysis-roster-confirmation`、`analysis-result-publication`、`player-report-evidence`和本批Context增量，不重定义通用创建模式或旧报告行为。

## Impact

- 前置：前两项Change获批准并实施，目标代码基线由负责人选定，真实参考/留出片段及数值质量profile预先批准。
- 拟影响`AnalysisJobCreate`的可选profile适配、现有提交/编排服务、分析确认与结果页及证据导出；不新增服务、消息系统或训练模型。
- 输入为经人工确认的研究Context；输出为受限片段结果、独立质量/复核状态和可追溯包。不默认复制或公开原始视频。
- 对应Notion PB-011/012/013/014/017/018。历史四人Change和动作分类Change继续独立管理，不将本profile验收当作原全片通过。
- 管理入口：[提案索引](https://app.notion.com/p/414f602574aa81a2bd37dd819f9833bf)、[PB-012 集成任务](https://app.notion.com/p/414f602574aa8140b3add643781a04b0?pvs=204)；Notion维护状态，本目录保存规格和验证依据。
- 风险是功能线未集成、测量误差缺参考、场边身份与metric资格混淆；先固定基准和误差门槛，依赖缺失时保留失败结论。
- 回滚为关闭新profile入口，保留旧Job及不可变研究结果；不得删除数据或回写历史质量。当前只交付提案，未授权Apply、合并、迁移、部署或Archive。
