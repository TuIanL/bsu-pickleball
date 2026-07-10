## ADDED Requirements

### Requirement: 双摄同步录制会话
系统 SHALL 提供双摄同步录制会话，用一次开始和一次停止操作同时管理两个已注册摄像头。两个摄像头均为平等机位，slot key 为 `cam_1` 和 `cam_2`，默认机位角度均为 `baseline_high`。

#### Scenario: 开始双摄同步录制
- **WHEN** 用户为 `cam_1` 和 `cam_2` 两个机位槽位选择了不同的已注册摄像头并点击开始同步录制
- **THEN** 系统创建一个双摄同步录制会话
- **AND** 系统为两路摄像头同时启动 FFmpeg 录制进程
- **AND** 系统记录会话 ID、Field Session ID、两个摄像头 ID、槽位、开始时间和输出目录

#### Scenario: 缺少任一机位时禁止开始
- **WHEN** 用户只选择了一个机位或两个机位选择了同一个摄像头并点击开始同步录制
- **THEN** 系统 MUST 拒绝开始录制
- **AND** 系统返回可展示的错误信息说明需要两个不同摄像头

#### Scenario: 摄像头被占用时禁止开始
- **WHEN** 任一被选摄像头已有活跃单摄或双摄录制会话
- **THEN** 系统 MUST 拒绝开始双摄同步录制
- **AND** 系统不得启动任何新的 FFmpeg 录制进程

### Requirement: 同步分段与异常重启
系统 SHALL 以同步分段方式保存两路视频，并在任一路异常或分段结束时同步重启所有路。

#### Scenario: 正常创建同步分段
- **WHEN** 双摄同步录制会话处于 recording 状态
- **THEN** 系统为每个分段写入两路视频文件
- **AND** 两路文件使用相同的分段编号
- **AND** 系统在会话 metadata 中记录每个分段的文件路径和状态

#### Scenario: 任一路异常退出后同步重启
- **WHEN** 任一路 FFmpeg 进程异常退出且用户未停止会话
- **THEN** 系统终止同一分段中的所有剩余 FFmpeg 进程
- **AND** 系统将当前分段标记为异常或中断
- **AND** 系统使用新的分段编号同步重启两路录制
- **AND** 系统记录最近错误信息和重启次数

#### Scenario: 用户停止录制
- **WHEN** 用户停止正在进行的双摄同步录制会话
- **THEN** 系统终止两路 FFmpeg 进程
- **AND** 系统等待录制线程退出
- **AND** 系统将会话状态更新为 completed
- **AND** 系统记录停止时间、总时长和已保存分段

### Requirement: 双摄短录测试
系统 SHALL 支持在正式录制前对两个摄像头执行短录测试。

#### Scenario: 执行短录测试
- **WHEN** 用户选择两个不同摄像头并请求短录测试
- **THEN** 系统使用同步录制核心录制一段短测试视频
- **AND** 系统为两路测试文件提取首帧和尾帧
- **AND** 系统返回每路测试结果、文件路径、首尾帧路径和错误信息
- **AND** 系统不得将测试结果创建为正式录制会话

#### Scenario: 短录测试失败
- **WHEN** 任一路摄像头无法录制测试分段
- **THEN** 系统返回失败状态
- **AND** 系统包含失败机位、摄像头 ID 和最近 FFmpeg 错误摘要

### Requirement: 默认分析视频登记
系统 SHALL 在双摄录制完成后使 `cam_1` 视频能够进入现有单视频分析流程（作为默认分析视频），并保留 `cam_2` 素材引用。

#### Scenario: 双摄录制完成后登记默认分析视频
- **WHEN** 双摄同步录制会话完成且 `cam_1` 存在可用视频产物
- **THEN** 系统将 `cam_1` 的合并视频登记为 `default_analysis_video_id`
- **AND** 系统保留 `cam_2` 的分段文件路径作为关联素材

#### Scenario: 默认分析视频无法登记
- **WHEN** 双摄同步录制完成但 `cam_1` 视频无法登记到现有视频系统
- **THEN** 系统仍 SHALL 保留双摄录制会话和文件路径
- **AND** 系统在会话中记录错误信息
- **AND** 前端不得展示不可用的创建分析入口

### Requirement: 短录测试首帧展示

系统 SHALL 在双摄短录测试结果中返回可直接访问的首帧 URL，并在前端展示缩略图。

#### Scenario: 测试完成后返回首帧 URL
- **WHEN** 用户完成双摄短录测试且首帧文件存在
- **THEN** 系统在测试响应中返回 `cam_1.first_frame_url` 和 `cam_2.first_frame_url`
- **AND** URL 为后端 static serve 提供的完整 HTTP 路径（`/api/sync-recordings/test-frames/...`）
- **AND** 前端仅需 `<img src={url}>` 渲染，不接触文件系统路径

#### Scenario: 首帧提取失败
- **WHEN** 短录测试完成但首帧文件不存在或无法读取
- **THEN** 系统返回 `first_frame_url: null` 或 `first_frame_exists: false`
- **AND** 前端展示占位提示「首帧不可用」
- **AND** 不影响测试通过/失败的整体判定

### Requirement: 双摄录制查询与状态展示
系统 SHALL 提供查询双摄同步录制会话状态的 API。

#### Scenario: 查询活跃双摄录制
- **WHEN** 前端查询正在录制的双摄会话
- **THEN** 系统返回会话状态、两个机位、当前分段编号、已保存分段数、重启次数和最近错误信息

#### Scenario: 查询已完成双摄录制
- **WHEN** 前端查询已完成的双摄会话
- **THEN** 系统返回开始时间、停止时间、总时长、所有分段摘要、主机位视频引用和副机位素材引用

### Requirement: 双摄同步录制 FPS 上限
系统 SHALL 将双摄同步录制的默认 FPS 和最高允许 FPS 设为 60fps。

#### Scenario: 双摄同步录制默认 60fps
- **WHEN** 用户打开双摄同步录制控制台且未手动修改视频帧率
- **THEN** FPS 控件 MUST 默认显示 60fps
- **AND** 开始同步录制请求 MUST 使用 `fps=60`

#### Scenario: 双摄同步录制选项最高为 60fps
- **WHEN** 用户查看双摄同步录制 FPS 控件
- **THEN** 控件 MUST 提供 60fps 选项
- **AND** 控件 MUST NOT 提供 90fps 或 120fps 选项

#### Scenario: 双摄同步录制 API 拒绝超过 60fps
- **WHEN** 客户端提交 `POST /api/sync-recordings/start` 且 `fps > 60`
- **THEN** 系统 MUST 拒绝该请求
- **AND** 系统 MUST NOT 创建双摄同步录制会话
- **AND** 系统 MUST NOT 启动任何 FFmpeg 录制进程

### Requirement: 双摄录制创建 CaptureTake

系统 MUST 在双摄录制启动时自动创建 CaptureTake 记录，支持事件打点。

#### Scenario: 双摄录制创建 CaptureTake

- **WHEN** 双摄同步录制启动成功
- **THEN** 系统 SHALL 创建 CaptureTake
- **AND** SHALL 为每个摄像头创建 CaptureTrack（含 offset_source/sync_quality）
- **AND** 响应 SHALL 包含 capture_take_id

#### Scenario: 双摄事件打点

- **WHEN** 用户处于双摄录制状态
- **THEN** 前端 SHALL 显示事件打点按钮
- **AND** 事件 SHALL 关联 CaptureTake
- **AND** timestamp_ms SHALL 相对 CaptureTake 开始时间
