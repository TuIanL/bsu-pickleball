## MODIFIED Requirements

### Requirement: Manual multi-anchor calibration preparation

系统 SHALL 支持在内置工作台使用至少 3 组、推荐 4-6 组跨越分析时间范围的共同事件锚点，通过后端 API 生成 `dual_camera_sync_calibration.v1`。每组锚点 SHALL 使用各 camera 的本地 source time；系统 SHALL 持久化原始锚点和生成结果，结果 SHALL 保存 reference camera、camera identity、offset、rate、drift、anchor count、residual、quality、valid interval 及素材 provenance。CLI SHALL 保留为维护和兼容入口，但用户 SHALL NOT 必须下载文件或运行 CLI 才能完成确认。

#### Scenario: 多锚点拟合质量良好
- **WHEN** 锚点至少 3 组、覆盖视频有效范围且拟合 residual 在配置阈值内
- **THEN** calibration SHALL 标记 `quality=good`
- **AND** SHALL 保存可复现的拟合参数、valid interval、原始锚点和素材 provenance
- **AND** CaptureTake 同步锚点状态 SHALL 可进入 `confirmed`

#### Scenario: 锚点不足或拟合质量不足
- **WHEN** 锚点少于 3 组、没有覆盖有效时间范围或 residual 超过阈值
- **THEN** calibration SHALL 标记为 `unknown` 或 `degraded`，或拒绝确认
- **AND** SHALL 保存结构化 reason
- **AND** SHALL NOT 被宣称为 authoritative good 或人工确认完成

#### Scenario: 通过内置工作台完成拟合
- **WHEN** 用户在系统内提交共同事件锚点
- **THEN** 后端 SHALL 复用与 CLI 相同的 payload 校验和拟合逻辑
- **AND** SHALL 将权威结果写入当前 CaptureTake 的约定时间线资产位置
- **AND** 用户 SHALL NOT 需要手工移动生成文件
