## MODIFIED Requirements

### Requirement: Field Session 采集控制台

系统 MUST 提供字段采集控制台，通过 `/capture/:id` 路由访问，按照「左预览、右控制、下事件标记和时间线」的布局组织摄像头预览、录制控制、场边事件标记和时间线功能。

#### Scenario: 创建后进入控制台
- **WHEN** 用户在三步向导中成功创建 Field Session
- **THEN** 前端 SHALL 自动导航到 `/capture/:id` 采集控制台
- **AND** 控制台 SHALL 展示任务名称、状态、采集模式、比赛形式、摄像头方案和场地信息
- **AND** 控制台按「左预览、右控制、下事件标记和时间线」布局渲染

#### Scenario: 在控制台复用摄像头能力
- **WHEN** 用户进入 Field Session 采集控制台
- **THEN** 前端 SHALL 保留摄像头预览、录制控制能力
- **AND** 摄像头列表 SHALL 通过设备抽屉访问，不直接展示在主界面
- **AND** 控制台设备状态区 SHALL 仅显示当前采集方案使用的摄像头
- **AND** 开始录制时 SHALL 将当前 Field Session id 传给后端

#### Scenario: 在控制台操作时间线事件
- **WHEN** 用户进入 Field Session 采集控制台且录制状态为 recording
- **THEN** 前端 SHALL 加载并展示该 Field Session 的 Session Timeline Event 列表
- **AND** 控制台 SHALL 提供场边事件快捷标记按钮（按 capture_mode 分类）
- **AND** 新事件 SHALL 实时追加到时间线末尾

#### Scenario: 录制完成展示面板
- **WHEN** 用户停止录制
- **THEN** 前端 SHALL 展示录制完成面板
- **AND** 面板内容根据向导中的分析设置（自动分析 / 再决定 / 仅保存）展示对应操作选项
- **AND** 面板可关闭，关闭后恢复到控制台预览状态

## REMOVED Requirements

### Requirement: 保留直接录制入口

**Reason**: 改版后所有录制都在 Field Session 上下文中进行，不再允许无 Field Session 的直接录制入口。
**Migration**: 用户必须先创建或选择一个 Field Session 才能进入录制，保证所有录制关联采集任务。
