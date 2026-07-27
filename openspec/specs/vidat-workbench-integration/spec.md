## ADDED Requirements

### Requirement: 一键打开 Vidat 工作台
系统 SHALL 允许用户从项目中为指定标注包打开本地 Vidat，并自动提供对应视频、标签配置和 annotation 文件。

#### Scenario: 打开成功
- **WHEN** 用户对一个有效标注包选择“在 Vidat 中编辑”
- **THEN** 系统 SHALL 返回包含该包视频、config 与 annotation 参数的本地工作台 URL
- **AND** SHALL 不要求用户手工移动或重命名文件

#### Scenario: 本地 Vidat 不可用
- **WHEN** 系统无法发现或启动配置的本地 Vidat 服务
- **THEN** 系统 SHALL 显示可执行的本地配置错误
- **AND** SHALL 保留已生成的标注包以供稍后打开

### Requirement: 命令行工作流兼容
系统 SHALL 保留命令行列出 CaptureTake、导出包、预览导入和打开 Vidat 的能力，并复用与 API 相同的格式校验。

#### Scenario: CLI 导出
- **WHEN** 用户使用 CLI 指定有效 CaptureTake
- **THEN** CLI SHALL 输出标注包版本、视频路径和 Vidat 打开 URL
- **AND** 生成的 manifest SHALL 满足 API 导出相同的字段与校验要求
