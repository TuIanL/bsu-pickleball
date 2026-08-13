## ADDED Requirements

### Requirement: CaptureTake 同步锚点时间线资产

系统 SHALL 将双摄同步锚点草稿、人工确认元数据和拟合 calibration 作为 CaptureTake 的版本化时间线资产持久化，并 SHALL 通过 CaptureTake 查询或专用 API 暴露当前状态摘要。AnalysisJob SHALL 引用该录制级权威结果，而不是复制一套任务级锚点。

#### Scenario: 保存录制级同步锚点
- **WHEN** 用户为双摄 CaptureTake 保存锚点草稿或确认结果
- **THEN** 资产 SHALL 写入该 CaptureTake 的时间线存储边界
- **AND** SHALL 记录 CaptureTake id、revision、camera identity、registered video identity 和 timing provenance

#### Scenario: 分析任务读取同步资产
- **WHEN** 系统为 CaptureTake 创建双摄 AnalysisJob
- **THEN** preflight SHALL 解析当前有效的录制级同步 calibration revision
- **AND** AnalysisJob SHALL NOT 创建独立且不可复用的锚点副本

#### Scenario: CaptureTake 详情暴露摘要
- **WHEN** 客户端查询双摄 CaptureTake 的同步锚点状态
- **THEN** API SHALL 返回状态、是否允许分析、来源、质量摘要、当前 revision 和失效原因
- **AND** 客户端 SHALL NOT 需要读取服务端文件系统路径推断状态

### Requirement: 同步锚点资产失效边界

系统 SHALL 基于素材 provenance 判断 CaptureTake 的人工同步确认是否仍然有效。会改变跨摄时间映射的素材或 timing 变化 SHALL 产生失效状态；AnalysisJob 生命周期和分析配置变化 SHALL 与录制级同步资产隔离。

#### Scenario: timing provenance 变化
- **WHEN** registered video 或 PTS sidecar 被重新生成且 identity 与确认版本不一致
- **THEN** 当前确认 SHALL 标记失效
- **AND** 旧 revision SHALL 保留用于审计

#### Scenario: 新建或删除 AnalysisJob
- **WHEN** 用户基于同一 CaptureTake 新建、重试或删除 AnalysisJob
- **THEN** CaptureTake 的同步锚点 revision SHALL NOT 因此改变
- **AND** 有效确认 SHALL 继续可复用
