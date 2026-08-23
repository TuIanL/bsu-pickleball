# vidat-workbench-integration Specification (delta)

## MODIFIED Requirements

### Requirement: 一键打开 Vidat 工作台
系统 SHALL 允许用户从项目中为指定标注包打开本地 Vidat，并自动提供对应视频、标签配置和 annotation 文件；系统 SHALL 同时展示受控服务状态和由平台打开的窗口状态。

#### Scenario: 打开成功
- **WHEN** 用户对一个有效标注包选择“在 Vidat 中编辑”
- **THEN** 系统 SHALL 返回包含该包视频、config 与 annotation 参数的本地工作台 URL
- **AND** SHALL 不要求用户手工移动或重命名文件
- **AND** SHALL 记录由平台打开的窗口引用（如果浏览器允许）

#### Scenario: 本地 Vidat 不可用
- **WHEN** 系统无法发现或启动配置的本地 Vidat 服务
- **THEN** 系统 SHALL 显示可执行的本地配置错误
- **AND** SHALL 保留已生成的标注包以供稍后打开

#### Scenario: 服务由其他进程占用
- **WHEN** Vidat URL 可访问但服务状态不属于本系统
- **THEN** 系统 SHALL 标记为未受控服务
- **AND** 停止按钮 SHALL 不得终止该进程

### Requirement: 命令行工作流兼容
系统 SHALL 保留命令行列出 CaptureTake、导出包、预览导入和打开 Vidat 的能力，并复用 API 的版本校验、元数据、派生、比较、删除和服务控制语义。

#### Scenario: CLI 导出
- **WHEN** 用户使用 CLI 指定有效 CaptureTake
- **THEN** CLI SHALL 输出标注包版本、名称、视频路径和 Vidat 打开 URL
- **AND** 生成的 manifest SHALL 满足 API 导出相同的字段与校验要求

#### Scenario: CLI 管理版本
- **WHEN** 用户通过 CLI 请求派生、比较、逻辑删除、永久清理或停止服务
- **THEN** CLI SHALL 调用与 API 相同的服务层语义
- **AND** SHALL 输出结果包 ID、保护原因或服务状态

## ADDED Requirements

### Requirement: 版本管理操作入口
系统 SHALL 在 Vidat 工作台为标注包提供导出命名、派生、元数据编辑、详细比较、逻辑删除和永久清理入口。

#### Scenario: 展示版本元信息
- **WHEN** 工作台列表显示一个标注包版本
- **THEN** 系统 SHALL 展示其名称、版本号与导入状态
- **AND** 在可用时展示负责人、备注、创建/导入时间、来源版本和当前投影状态

#### Scenario: 从当前版本派生
- **WHEN** 用户对当前选中的标注包选择“派生新版本”并提供名称/负责人/备注
- **THEN** 系统 SHALL 调用派生接口并刷新版本列表

#### Scenario: 普通导出时填写元数据
- **WHEN** 用户选择“导出新版本”并填写名称、负责人或备注
- **THEN** 系统 SHALL 将这些元数据提交给创建接口
- **AND** SHALL 在导出成功后选中新生成的 `generated` 版本

#### Scenario: 重命名当前版本
- **WHEN** 用户对当前选中的标注包编辑名称、负责人或备注并提交
- **THEN** 系统 SHALL 调用更新接口并刷新展示

#### Scenario: 比较两个版本
- **WHEN** 用户选择同一 CaptureTake 下的两个版本并点击“比较版本”
- **THEN** 系统 SHALL 展示两侧元信息、统计摘要和事件级差异
- **AND** SHALL 按新增、删除、移动、类型、胜者和比分锚点变化分组展示
- **AND** 比较 SHALL 不修改当前投影

#### Scenario: 逻辑删除当前列表中的历史版本
- **WHEN** 用户确认删除一个不是当前 Vidat 投影的标注包版本
- **THEN** 系统 SHALL 调用逻辑删除接口
- **AND** 删除成功后 SHALL 从默认列表移除并在必要时自动选中剩余版本
- **AND** SHALL 明确提示审计和快照仍被保留

#### Scenario: 永久清理受保护版本
- **WHEN** 用户请求永久清理一个存在审计、预览、当前投影或子派生关系的版本
- **THEN** 系统 SHALL 阻止操作
- **AND** SHALL 展示后端返回的具体保护原因

### Requirement: 关闭 Vidat 工作台
系统 SHALL 允许用户分别关闭由平台打开的 Vidat 窗口和停止受本系统控制的本地 Vidat 静态服务。

#### Scenario: 关闭平台打开的窗口
- **WHEN** 用户在工作台点击“关闭 Vidat 标签页”且窗口由平台打开
- **THEN** 系统 SHALL 尝试关闭该窗口
- **AND** 关闭失败时 SHALL 提示用户手工关闭标签页

#### Scenario: 停止服务
- **WHEN** 用户在工作台点击“停止 Vidat 服务”
- **THEN** 系统 SHALL 调用停止服务接口
- **AND** 停止成功 SHALL 提示服务已停止并释放地址
- **AND** 服务未运行或不是本系统控制的进程 SHALL 提示当前状态且不得误杀其他进程
