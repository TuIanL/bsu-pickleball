# Design

## Context

现有main支持完整legacy任务及三个模块专项能力；功能线43b5727新增联合人/姿态/球同源帧产物、分段回放和checkpoint，尚未合入main。最新30–587.15s完整流程成功而严格四人仍FAIL；因此首版必须固定受控片段、保留失败并独立验证科研指标。

该变更跨API、现有编排、前端、复核和导出，需设计。它不包含旧四人算法或动作分类的全部未完成项，避免用产品流程Change替代算法验收。

## Goals / Non-Goals

**Goals:** 在现有流程增加可回滚的研究profile，复用确认、执行和回放；使必需证据、质量与人工修订闭合。

**Non-Goals:** 不开发硬件、多模态、判罚、全片自动理解、自动教练评分，不更换模型骨干，不全量迁移modular，不将历史全段FAIL改为pass。

## Decisions

### D1 可选profile而非第二套分析服务

建议在`AnalysisJobCreate`增加可选`analysisProfile`及`researchContext`；不带profile的请求走原逻辑。`research_clip_v1`要求Context、批准的质量profile和已确认输入。仍用现有Job/Worker/受控产物接口；快照以版本化Job载荷和不可变文件保存，首版不要求DDL。

正式研究请求缺输入时给明确错误；普通实验入口保留现有降级语义。替代方案是新独立服务或全modular重建，会扩大首版交付范围，故不采用。

### D2 先明确必需输出，隔离可选依赖

必需为人物确认与位置证据、描述性指标、回放与证据包。姿态/球/事件等按请求独立执行和报告，不自动加载无关模型。先复用完整引擎可用边界，不把modular planned条目假装可执行。相关旧引擎若有强制前置阶段，应在批准后做最小profile适配，不复制完整pipeline。

研究profile所用目标代码须经PB-010/ADR-004批准。若需功能线代码则单独Review其集成，不在本项自动合并27提交；适配面通过已批准接口使用联合源帧产物。既有算法缺陷先保留fail或按原Change修复。

### D3 人工复核与导出追加版本

建议新增受既有API边界保护的`POST /api/analysis/jobs/{id}/research-reviews`，保存review revision、目标Artifact/ObjectRef、原值、新值、原因、实际源帧与复核来源。它不直接修改源观测，也不把自由文本reviewer名称宣称为已认证人员。

建议`GET /api/analysis/jobs/{id}/research-package`读取已发布包。包由manifest.json、context.json、results引用/小型数据表、metrics.csv及reviews.json组成；复用第一项Manifest校验与现有受控Job产物路径，内部staging成功后发布。大视频与密钥/个人位置映射不默认导出。重跑绑定新Context或review revision，新旧版本并存。

### D4 页面优先确认和证据回跳

复用NewAnalysis/RecordingAnalyze/MultiViewAnalysisSetup及现有名册/标定组件，研究选择仅展示科研人员所需操作。提交前显示片段和输入是否齐备；结果复用VideoAnalysisCard/报告证据适配器，按本机位源帧读取并保持统一时间。实现细节、缓存键和内部调试字段不成为普通产品步骤。

复核时明确实测、预测、PROJ、匿名和缺失；不从demoData补真实结果。导出读取同一版本结论，不在前端重新算指标或推断缺失主体。

## Risks / Trade-offs

- 真实标签/科研容限不足 → PB-011先冻结质量profile；无批准只保留实验结果，不给R1科研验收pass。
- 场边人物仍可见而空间无效 → Context独立表达身份与metric资格，历史全段失败保留。
- 功能线集成不确定 → 基线批准先于Apply；先用合同fixtures验证边界，不自动扩展改动范围。
- 大JSON回放 → 经评审复用功能线分段接口，不能新建整片浏览器缓存。
- 人工修订混淆真值 → 原始算法和人工修订分开版本，独立参考集不用于反向调参。

## Migration Plan

批准顺序为前两Change→基线/质量profile→本项Apply。先用隔离数据库/输出根验证创建、失败、取消和导出；再对预先固定的参考/留出片段运行真实链路，保留输入/输出摘要及独立复核证据。未完成独立标签/误差验证时停留待验收。

研究profile默认不启用；部署时经批准显式开放。回滚关闭profile新提交和复核写入口，保留旧读取与结果；不删除Schema或旧Job、不反向迁移真实数据。未获授权不运行部署、模型发布、Archive或PR合并。

## Acceptance Gates

依据specs/research-clip-review-workflow/spec.md逐项Verify：原请求兼容、缺确认拒绝、冻结窗口、缺失分母、同机位源帧、可选失败、追加修订及包内外同源。真实科研误差满足预先批准profile；明确区分契约pass、算法质量和负责人验收。
