# vidat-annotation-package Specification

## Purpose

定义可复现的 Vidat 标注包、版本刷新、历史留存和训练标注查询的文件与生命周期契约，确保发布包内容稳定、可追踪且可供训练流程消费。
## Requirements
### Requirement: 可复现的 Vidat 标注包
系统 SHALL 为视频就绪的 CaptureTake 创建版本化且内容不可变的 Vidat 标注包；包可通过元数据管理，但 `manifest`、annotation 和规范化快照不得被元数据操作覆盖。

#### Scenario: 创建带元数据的标注包
- **WHEN** 用户为已完成且有可播放主视频的 CaptureTake 请求导出，并可选提供 `name`、`owner`、`note`
- **THEN** 系统 SHALL 创建新的不可变包版本
- **AND** manifest SHALL 包含 CaptureTake ID、源 timeline revision、视频 fingerprint、FPS、时长和导出时间
- **AND** 未提供名称时 SHALL 展示“第 N 版”

#### Scenario: 视频未就绪
- **WHEN** CaptureTake 没有有效主视频或双摄视频尚未合并完成
- **THEN** 系统 SHALL 拒绝创建标注包
- **AND** SHALL 返回视频未就绪的明确状态

### Requirement: 标注包刷新不覆盖历史版本
系统 MUST 在刷新导出、派生或确认导入时创建新版本，不得覆盖已创建或已导入的归档包内容；逻辑删除不得改变已保存的快照。

#### Scenario: 刷新已有标注包
- **WHEN** 用户请求刷新一个 CaptureTake 的 Vidat 导出
- **THEN** 系统 SHALL 创建新的包版本和 manifest
- **AND** 旧版本 SHALL 保持可读取和可用于审计

#### Scenario: 导入生成结果版本
- **WHEN** 用户确认某个版本的有效 Vidat 导入预览
- **THEN** 系统 SHALL 创建新的 `derived` 结果版本
- **AND** 来源版本的 annotation、manifest 和规范化快照 SHALL 保持不变

### Requirement: 训练标注留存
系统 MUST 保留导入前的原始 Vidat JSON、确认后的规范化语义快照和来源/结果版本关系，以便后续数据集转换和审计复现。

#### Scenario: 确认导入后查询历史
- **WHEN** 一个标注包版本被确认导入
- **THEN** 系统 SHALL 保留来源包和结果包的原始 JSON、manifest、规范化快照及导入审计
- **AND** SHALL 允许按 CaptureTake、包版本和 lineage 查询这些工件

### Requirement: 标注包元数据
系统 SHALL 为标注包提供可自定义的名称、负责人和备注元数据，用于分工与协作对账。

#### Scenario: 默认名称
- **WHEN** 用户导出或派生一个标注包而未指定名称
- **THEN** 系统 SHALL 使用默认名称“第 N 版”（N 为该包版本号）
- **AND** 该包可被按名称在列表/下拉中展示

#### Scenario: 自定义名称与负责人/备注
- **WHEN** 用户导出或派生标注包时提供 `name`、`owner`、`note`
- **THEN** 系统 SHALL 持久化这些字段
- **AND** 列表返回 SHALL 包含这些字段

#### Scenario: 更新元数据
- **WHEN** 用户对已存在的标注包更新名称、负责人或备注
- **THEN** 系统 SHALL 仅更新被提交的字段
- **AND** 未提交字段保持不变

#### Scenario: 导出时自定义名称
- **WHEN** 用户在普通导出时提供自定义名称、负责人或备注
- **THEN** 系统 SHALL 在创建包时保存这些元数据
- **AND** SHALL 将普通导出标记为 `provenance=generated`

### Requirement: 派生版本
系统 SHALL 允许用户从任意已有标注包版本派生一个新版本，并复制源版本的内容作为标注基线。

#### Scenario: 从既有版本派生
- **WHEN** 用户选择某个标注包版本并请求派生
- **THEN** 系统 SHALL 创建新版本并复制源包的 annotation 内容
- **AND** SHALL 重写新包的 `pickleball_manifest.package_id`、manifest 包 ID/版本和文件引用
- **AND** 新版本 SHALL 记录 `source_package_id`（派生源）与 `provenance=derived`
- **AND** 源版本 SHALL 保持不变

#### Scenario: 派生版本独立演进
- **WHEN** 用户随后导入或修改派生后的版本
- **THEN** 系统 SHALL 不影响源版本及其历史
- **AND** 派生包作为独立版本继续累积

### Requirement: 标注包删除与永久清理
系统 SHALL 支持逻辑删除标注包版本，并在满足审计和 lineage 保护条件时支持永久清理。

#### Scenario: 逻辑删除版本
- **WHEN** 用户删除一个不是当前 Vidat 投影的标注包版本
- **THEN** 系统 SHALL 设置 `deleted_at` 并从默认版本列表中隐藏
- **AND** SHALL 保留数据库快照、导入审计和 lineage 信息
- **AND** SHALL 清理该包在 Vidat dist 中的发布文件

#### Scenario: 永久清理未受保护版本
- **WHEN** 用户请求永久清理一个没有审计/预览引用、不是当前投影且没有未删除子派生包的版本
- **THEN** 系统 SHALL 校验目录位于受控数据根目录
- **AND** SHALL 删除 package 目录、发布残留和数据库记录

#### Scenario: 永久清理受保护版本被拒绝
- **WHEN** 用户请求永久清理一个被审计、预览、当前投影或未删除子派生关系引用的版本
- **THEN** 系统 SHALL 拒绝清理
- **AND** SHALL 返回具体的保护原因

#### Scenario: 当前投影不能直接删除
- **WHEN** 用户删除当前 Vidat 投影对应的版本
- **THEN** 系统 SHALL 拒绝删除或要求先切换到其他有效版本
- **AND** SHALL 不改变当前比赛投影

### Requirement: 版本详细对比
系统 SHALL 提供同一 CaptureTake 下两个标注包版本的元信息、统计摘要和事件级差异对比。

#### Scenario: 对比两个版本
- **WHEN** 用户对同一 CaptureTake 下两个不同版本请求对比
- **THEN** 系统 SHALL 返回两版的 `version`、`name`、`provenance`、`source_package_id`、`created_at`、`imported_at`
- **AND** 返回操作数、编码动作数、最终比分与最终胜者等汇总统计
- **AND** 返回新增、删除、移动、事件类型、胜者、比分锚点和其他字段变化
- **AND** 对比 SHALL 不修改当前 Vidat 投影或任何包内容

#### Scenario: 比较不同 CaptureTake 的版本
- **WHEN** 用户请求比较不属于同一 CaptureTake 的两个包
- **THEN** 系统 SHALL 拒绝比较
- **AND** SHALL 返回明确的范围错误

