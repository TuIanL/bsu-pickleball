## ADDED Requirements

### Requirement: 可复现的 Vidat 标注包
系统 SHALL 为视频就绪的 CaptureTake 创建版本化 Vidat 标注包，包含 manifest、Vidat annotation JSON、匹克球标签配置和视频访问引用。

#### Scenario: 创建标注包
- **WHEN** 用户为已完成且有可播放主视频的 CaptureTake 请求导出
- **THEN** 系统 SHALL 创建不可变的标注包版本
- **AND** manifest SHALL 包含 CaptureTake ID、源 timeline revision、视频 fingerprint、FPS、时长和导出时间

#### Scenario: 视频未就绪
- **WHEN** CaptureTake 没有有效主视频或双摄视频尚未合并完成
- **THEN** 系统 SHALL 拒绝创建标注包
- **AND** SHALL 返回视频未就绪的明确状态

### Requirement: 标注包刷新不覆盖历史版本
系统 MUST 在刷新导出时创建新版本，不得覆盖已创建或已导入的标注包内容。

#### Scenario: 刷新已有标注包
- **WHEN** 用户请求刷新一个 CaptureTake 的 Vidat 导出
- **THEN** 系统 SHALL 创建新的包版本和 manifest
- **AND** 旧版本 SHALL 保持可读取和可用于审计

### Requirement: 训练标注留存
系统 MUST 保留导入前的原始 Vidat JSON 与确认后的规范化语义快照，以便后续数据集转换复现。

#### Scenario: 确认导入后查询历史
- **WHEN** 一个标注包版本被确认导入
- **THEN** 系统 SHALL 保留该版本的原始 JSON、manifest 和规范化快照
- **AND** SHALL 允许按 CaptureTake 和包版本查询这些工件
