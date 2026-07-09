## MODIFIED Requirements

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

## ADDED Requirements

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
