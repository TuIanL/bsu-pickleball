# Design

## Context

已有`analysis-context-contract`定义五项通用要求，`AnalysisJobCreate`含videoId、calibrationId、clipStartMs/clipEndMs、roster及multiview输入；`analysis_runtime/contracts`支持冻结上下文、单位和独立状态。新增研究合同应复用这些身份及语义，避免第二套时钟或P编号映射。

本项跨时间、身份与历史标注语义，存在兼容复杂性，需明确设计。旧PB-DATA-SPEC-001 V1.0仅作历史参考；已读取其表格，不据其试行阈值或主类改变当前数据。

## Goals / Non-Goals

**Goals:** 用纯类型、导入适配和fixtures定义可验证研究Context及结果引用，供下一Change接入。

**Non-Goals:** 不运行模型、不开放新页面、不迁移真实数据库、不修改已发布标注/模型、不将planned能力改为implemented。

## Decisions

### D1 研究快照采用组合合同

建议新增`ResearchClipContext`：schema_version、evidence_package_ref、source_refs、source_frame_ranges、requested_window、context_window_policy、time_mapping_snapshot、roster_snapshot_ref、calibration_refs、quality_profile_ref及manual_confirmation_refs。规范化内容摘要由消费端验证，不能只相信调用者声称已批准。

采用组合已有引用，避免复制大payload；纯类型模块不得加载cv2/torch。上游Manifest稳定后再实施适配。替代方案是重写整个AnalysisJobCreate，将扩大兼容范围，故不采用。

### D2 保留三种时间和明确末端

每路保存source frame index、source PTS/timebase及take映射revision/hash/有效域。输入包含式帧区间与内部半开毫秒窗口分别存储。已核验CFR可用有理数fps转换；VFR按实际帧PTS及有效帧末端，未知末端返回结构化错误，不推算确定时间。

保留请求、实际处理上下文与指标选择范围。双摄锚点可用域外的外推帧仅按已有时钟策略标记，不提升为正式感知。位置/身份变更不能使不消费它们的纯检测缓存失效。

### D3 主体、单位和质量分别建类型

Session匿名人员、P槽位、view-local track+epoch、global ID经显式关联连接。保存identity_confirmed、real_observation与metric_eligibility及原因，不能把场边有效身份等同场内指标资格。

空间保持现有ft合同；米制导出用1ft=0.3048m的显式版本化转换，记录原点、轴向、标定与有效域。图像关键点只能输出对应图像量纲，平面Homography不生成3D生物力学结论。

执行终态、availability、completeness、算法quality和review状态独立。QualityProfile是先批准后引用的外部配置；数值尚未批准时输出原始误差并待审，不设默认科研pass。

### D4 旧规范采用独立来源版本

保存旧规范文件hash及历史地位。return主类不能无损映射到具体击球技术；合并Dink/Volley时保留原侧别，缺信息保持unknown。当前stroke_side与hand_usage不合并；COCO17和Halpe26只对显式对应点建立派生视图，模型score不转换为人工可见性。

此处批准的是“保存版本与不猜补”行为，具体taxonomy采纳仍由ADR-002评审。无需等待其选择即可设计不损失信息的引用合同，也不得在本项代替原始标注。

## Risks / Trade-offs

- VFR或末端证据不足 → 拒绝精确换算，保留原始帧地址。
- P/track/global语义冲突 → 校验作用域、epoch、唯一映射与来源，不按字符串尾号配对。
- 多坐标约定 → 显式适配，原始单位保留；无标定时不输出米制指标。
- 历史数据与研究Profile批准脱节 → 对每次修订保留引用和批准依据；无批准不得研究验收pass。

## Migration Plan

批准后新增纯类型与JSON Schema，构建CFR/VFR、双摄不同源帧、旧标签和缺失状态fixtures。给legacy/modular建立只读兼容适配，不改变原默认入口。与上游真实参考Manifest联合核验，未知历史字段不回写。

回滚为关闭新适配路径，保留版本化Context和读取；无DDL、原Schema破坏或数据重标。后续研究profile接入属于独立Change。

## Review Gates

对应PB-007/008/009；依赖前项资产身份合同及参考包。Apply前逐项Review，质量阈值的具体值由PB-011/ADR-003批准，不能将方向确认视为类型/阈值已批准。
