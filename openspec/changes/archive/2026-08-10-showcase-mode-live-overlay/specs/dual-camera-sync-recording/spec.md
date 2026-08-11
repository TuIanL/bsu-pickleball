## ADDED Requirements

### Requirement: 双摄录制中的展示旁路接线

系统 SHALL 根据关联 Field Session 的 `display_mode` 决定是否在双摄录制期间启动实时展示旁路，且 SHALL 不改变双摄原始录制、CaptureTake 终态化和停止后合并契约。

#### Scenario: 展示模式开始双摄录制

- **WHEN** `display_mode=showcase` 的 Field Session 成功开始双摄录制
- **THEN** 系统 SHALL 启动与该 CaptureTake 绑定的 ShowcaseRuntime
- **AND** 双摄 FFmpeg 录制 SHALL 继续写入既有原始分段
- **AND** 录制响应或运行状态 SHALL 能让前端发现展示运行引用

#### Scenario: 标准模式开始双摄录制

- **WHEN** `display_mode=standard` 的 Field Session 成功开始双摄录制
- **THEN** 系统 SHALL 不启动实时展示旁路
- **AND** 既有双摄录制响应、分段和状态 SHALL 保持兼容

### Requirement: 展示旁路错误隔离

系统 SHALL 将 ShowcaseRuntime 的启动、读取、推理和输出错误与双摄原始录制错误分开管理。

#### Scenario: 展示模型启动失败

- **WHEN** 双摄录制已经成功启动但展示模型无法加载
- **THEN** 双摄录制 SHALL 保持 recording
- **AND** 展示状态 SHALL 记录模型不可用原因
- **AND** 前端 SHALL 能显示展示降级或普通预览回退状态

#### Scenario: 单路展示流断开

- **WHEN** cam_1 或 cam_2 的展示流读取失败
- **THEN** 失败机位 SHALL 标记为 unavailable 或 failed
- **AND** 另一机位的展示流和两路原始录制 SHALL 不因该失败自动终止

### Requirement: 停止顺序与正式分析衔接

系统 SHALL 在双摄录制停止时回收 ShowcaseRuntime，并 SHALL 保持现有录制完成、合并和正式分析入口行为。

#### Scenario: 正常停止展示录制

- **WHEN** 用户停止 `display_mode=showcase` 的双摄录制
- **THEN** 系统 SHALL 请求展示旁路停止并释放其摄像头读取、推理、队列和订阅资源
- **AND** 系统 SHALL 按现有流程收尾原始双摄录制并持久化 CaptureTake
- **AND** 后续视频合并和完整分析 SHALL 使用原始录制产物，而不是实时叠加帧

#### Scenario: 展示旁路停止超时

- **WHEN** ShowcaseRuntime 在限定时间内未完成停止
- **THEN** 系统 SHALL 记录可解释的旁路停止警告
- **AND** 系统 SHALL 继续执行原始双摄录制的安全收尾
- **AND** 系统 SHALL 不因展示旁路停止超时删除原始分段或阻止后续分析入口
