## ADDED Requirements

### Requirement: 摄像头实时预览 API

系统 MUST 提供浏览器可直接显示的摄像头实时预览流，用于在录制前确认摄像头画面。

#### Scenario: 打开已注册摄像头预览
- **WHEN** 用户请求 `GET /api/cameras/{camera_id}/preview` 且摄像头已注册并可读取视频帧
- **THEN** 系统 SHALL 返回 `multipart/x-mixed-replace` 响应
- **AND** 响应 SHALL 持续输出 JPEG 帧
- **AND** 帧内容 SHALL 来自该摄像头当前视频流

#### Scenario: 预览不存在的摄像头
- **WHEN** 用户请求不存在的 `camera_id` 的预览流
- **THEN** 系统 SHALL 返回 404
- **AND** 错误信息 SHALL 表明摄像头不存在

#### Scenario: 摄像头流不可读
- **WHEN** 摄像头已注册但流地址不可达、鉴权失败或无法读取帧
- **THEN** 系统 SHALL 返回可被前端识别的失败响应
- **AND** 系统 SHALL 不创建录制 session
- **AND** 系统 SHALL 释放已打开的摄像头资源

#### Scenario: 客户端断开预览
- **WHEN** 浏览器离开页面、切换摄像头或停止加载预览流
- **THEN** 系统 SHALL 停止该预览响应的帧读取循环
- **AND** 系统 SHALL 释放对应的 `VideoCapture` 或等价资源

### Requirement: 球场采集页面预览体验

系统 MUST 在球场采集页面根据当前选择的摄像头展示实时预览状态。

#### Scenario: 未选择摄像头
- **WHEN** 用户尚未在开始录制表单中选择摄像头
- **THEN** 页面 SHALL 显示稳定的未选择状态
- **AND** 页面 SHALL 不请求摄像头预览流

#### Scenario: 选择摄像头后显示预览
- **WHEN** 用户选择一个已注册摄像头
- **THEN** 页面 SHALL 请求该摄像头的预览流
- **AND** 页面 SHALL 在预览区域显示实时画面

#### Scenario: 切换摄像头
- **WHEN** 用户从一个摄像头切换到另一个摄像头
- **THEN** 页面 SHALL 停止使用旧摄像头预览 URL
- **AND** 页面 SHALL 加载新摄像头预览 URL

#### Scenario: 预览加载失败
- **WHEN** 预览流请求失败或浏览器无法加载预览画面
- **THEN** 页面 SHALL 显示预览失败状态
- **AND** 页面 SHALL 保留录制表单和摄像头探测操作可用

### Requirement: 预览资源约束

系统 MUST 限制实时预览对本地运行环境和摄像头设备的资源压力。

#### Scenario: 预览帧率限制
- **WHEN** 系统输出摄像头预览帧
- **THEN** 系统 SHALL 以受控帧率输出预览画面
- **AND** 预览帧率 SHALL 不依赖摄像头原始帧率无限制输出

#### Scenario: 预览不改变录制状态
- **WHEN** 用户仅打开或关闭摄像头预览
- **THEN** 系统 SHALL 不创建、停止、取消或修改任何录制 session
