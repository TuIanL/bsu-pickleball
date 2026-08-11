## ADDED Requirements

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
