# multiview-timing-authority delta

## MODIFIED Requirements

### Requirement: Historical registered video sidecar materialization

系统 SHALL 支持对已完成历史 CaptureTake 的最终 registered video 幂等生成 `<registered_video_path>.pts.jsonl`，并 SHALL 使用现有 PTS sidecar writer 提取 `best_effort_timestamp_time`。生成过程 SHALL 使用临时文件和原子替换，不得修改或覆盖原始 TS、registered video 或已有有效 sidecar。

系统 SHALL 通过多个触发源驱动该补写，使 sidecar 与视频同生命周期：

- **materialize API**：系统 SHALL 提供 `POST /api/videos/{video_id}/timing/materialize` 同步补写接口。接口 SHALL 对 registered video 幂等生成 sidecar；sidecar 已存在且有效 SHALL 直接复用并返回现有 summary；视频不存在或不可用 SHALL 返回结构化 404；生成失败 SHALL 返回结构化 409 且不得影响媒体本身。
- **启动扫描**：系统启动时 SHALL 扫描全部 registered videos（含 sync-recording 会话注册的视频），对缺失 sidecar 的异步补写。扫描与补写 SHALL 并发受限（默认 1），外接盘未挂载、媒体文件缺失或 ffprobe 失败 SHALL 仅记录 warning 并以 `missing`/unavailable 降级，SHALL NOT 阻塞启动。
- **merge 收尾补强**：`request_merge` 对 `merge_status == completed` 且视频已注册的会话 SHALL 仍校验每路 registered video 的 sidecar，缺失 SHALL 补写（幂等快路径），使"merge 完成"与"timing 可用"同生命周期。

同一视频的多个触发源并发补写 SHALL 通过 per-video 锁串行化，避免重复 ffprobe；原子写入保证任一触发源成功即终止其余竞争。

#### Scenario: registered video 可生成 sidecar
- **WHEN** registered video 可读取且 ffprobe 返回非空、有限、单调的 frame PTS
- **THEN** 系统 SHALL 写入对应 sidecar
- **AND** sidecar SHALL 记录 frame index、PTS、可用 DTS 和 keyframe provenance

#### Scenario: sidecar 已存在且有效
- **WHEN** 对应 sidecar 已存在且 frame index/PTS 校验通过
- **THEN** 系统 SHALL 复用该 sidecar
- **AND** SHALL NOT 重复扫描或覆盖它

#### Scenario: 通过 materialize API 修复缺失 sidecar
- **WHEN** 客户端对缺失 sidecar 的 registered video 调用 `POST /api/videos/{video_id}/timing/materialize` 且补写成功
- **THEN** API SHALL 返回 sidecar summary（frame count、FPS、首尾 PTS）
- **AND** 随后的 `GET /api/videos/{video_id}/timing` SHALL 返回 `source_pts` authority

#### Scenario: materialize 补写失败
- **WHEN** 媒体不可读取、ffprobe 超时、PTS 非有限或不单调
- **THEN** API SHALL 返回结构化 409（含 reason）
- **AND** registered video 与既有媒体 SHALL 保持不变
- **AND** timing authority SHALL 保持 `missing`/unavailable

#### Scenario: 启动扫描自愈历史会话
- **WHEN** 后端启动且存在缺失 sidecar 的 registered video（如 8-13 之前完成 merge 的会话）
- **THEN** 系统 SHALL 在后台自动补写缺失 sidecar
- **AND** 补写完成后 `GET /api/videos/{video_id}/timing` SHALL 返回 `source_pts` authority
- **AND** 启动过程 SHALL 不被补写任务阻塞

#### Scenario: 启动扫描遇到外接盘未挂载
- **WHEN** 启动扫描时媒体所在卷不可用或媒体文件缺失
- **THEN** 系统 SHALL 记录 warning 并跳过该视频
- **AND** 其他视频的补写 SHALL 不受影响
- **AND** 后端 SHALL 正常完成启动
