# camera-live-preview Specification

## Purpose
Define the camera live preview capability — MJPEG over HTTP streaming from RTSP/RTMP/HTTP cameras for browser display, with controlled framerate and proper resource lifecycle management.
## Requirements
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

### Requirement: 展示模式叠加预览流

系统 SHALL 为活动 ShowcaseRuntime 提供按机位读取的浏览器可显示叠加预览流，并 SHALL 保留现有不带叠加的普通摄像头预览接口。

#### Scenario: 读取 cam_1 展示流

- **WHEN** 展示屏请求活动 ShowcaseRuntime 的 cam_1 流
- **THEN** 系统 SHALL 返回持续输出 JPEG 帧的 `multipart/x-mixed-replace` 响应或等价浏览器流
- **AND** 帧 SHALL 来自当前 cam_1 摄像头
- **AND** 可用时帧 SHALL 包含人体框和实时展示标识

#### Scenario: 读取 cam_2 展示流

- **WHEN** 展示屏请求活动 ShowcaseRuntime 的 cam_2 流
- **THEN** 系统 SHALL 返回当前 cam_2 的叠加预览帧
- **AND** cam_2 帧 SHALL 不混入 cam_1 的检测框、球点或轨迹

#### Scenario: 展示运行不存在或已停止

- **WHEN** 客户端请求不存在、已停止或不属于当前 CaptureTake 的 ShowcaseRuntime 流
- **THEN** 系统 SHALL 返回 404、410 或等价的可识别失效响应
- **AND** 系统 SHALL 不重新打开摄像头流或创建新的录制 session

### Requirement: 普通预览兼容

系统 SHALL 保持 `/api/cameras/{camera_id}/preview` 的原始预览语义，展示模式的叠加流不得改变标准模式的预览资源行为。

#### Scenario: 标准模式打开预览

- **WHEN** 标准模式用户打开普通摄像头预览
- **THEN** 系统 SHALL 输出不带实时模型叠加的摄像头画面
- **AND** 系统 SHALL 不启动 ShowcaseRuntime

#### Scenario: 关闭展示流

- **WHEN** 展示屏关闭叠加预览且双摄录制仍在进行
- **THEN** 系统 SHALL 释放展示流订阅
- **AND** 原始双摄录制 SHALL 继续

### Requirement: 展示预览资源受控

系统 SHALL 对每个 ShowcaseRuntime 机位限制输入读取、推理、JPEG 编码和订阅队列资源，并 SHALL 在客户端断开或会话停止时释放资源。

#### Scenario: 多个展示客户端订阅同一路

- **WHEN** 多个展示客户端订阅同一机位
- **THEN** 系统 SHALL 复用该 ShowcaseRuntime 机位的读取和推理结果
- **AND** 系统 SHALL 不为每个客户端独立创建一个 YOLO 推理循环

#### Scenario: 摄像头流不可读

- **WHEN** 展示机位流不可达或读取失败
- **THEN** 该机位展示状态 SHALL 标记失败并提供原因
- **AND** 其他机位展示流和原始双摄录制 SHALL 按独立状态继续运行

