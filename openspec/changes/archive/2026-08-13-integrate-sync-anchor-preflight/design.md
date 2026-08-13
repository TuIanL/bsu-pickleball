## Context

系统已有 `SyncCalibrationWorkbenchPage`、source PTS timing API、多锚点验证/拟合函数以及约定路径 `timeline/sync_calibration.json`。但工作台当前只把草稿存入浏览器 `localStorage` 并导出 JSON，权威校准仍依赖 `calibrate_dual_camera_sync.py`；分析创建时则可能自动生成 `auto_degraded_from_recording_timing` 文件。由于 `CaptureTakeSummary` 不暴露同步锚点状态，前端无法判断文件是人工确认还是自动估算，也无法把标注作为可恢复的分析前置任务。

本变更横跨 CaptureTake API、时间线文件资产、多锚点拟合服务、双摄分析 preflight 和两个前端页面。主要使用者是发起双摄分析的业务用户；维护脚本和现有历史 CaptureTake 仍需兼容。

## Goals / Non-Goals

**Goals:**

- 在系统内完成锚点草稿、拟合、确认和返回分析向导的闭环。
- 让人工锚点结果归属于 CaptureTake，并在后续 AnalysisJob 中复用。
- 用明确状态区分人工确认、自动降级、无需标注、待标注、草稿和失效。
- 在前端推进步骤和后端创建任务两个位置执行一致的同步前置门禁。
- 对会改变跨摄时间映射的素材变化执行可解释的失效判断。

**Non-Goals:**

- 不实现自动视觉事件匹配或自动推荐锚点。
- 不改变现有线性 offset/rate 拟合算法，也不引入新的外部依赖。
- 不把球场四角标定与同步锚点合并成同一种标定资产。
- 不移除 CLI；CLI 继续用于维护、批处理和兼容导入。
- 不在本变更中提供完整的历史版本浏览/回滚 UI。

## Decisions

### 1. 同步锚点资产归属 CaptureTake

草稿、确认元数据和拟合 calibration 存放在 CaptureTake 的 `timeline` 存储边界，AnalysisJob 仅解析当前有效 revision。建议资产结构为：

```text
<take>/timeline/
  sync_anchor_draft.json
  sync_anchors.v1.json
  sync_calibration.json
  sync_anchor_confirmation.json
```

所有写入使用临时文件加原子替换；确认操作在服务层完成全量校验后依次生成一组具有同一 revision/provenance 的资产。`sync_calibration.json` 保持现有消费者约定，避免修改多视角执行器读取路径。

备选方案是在 `capture_takes` 表增加 JSON 字段。未采用，因为锚点内容和 calibration 已是文件型时间线资产，重复存储会产生双权威；数据库迁移也不能解决现有执行器直接读取约定文件的问题。

### 2. 专用状态 API，不以文件存在性推断人工确认

在 `/api/capture-takes/{id}/sync-anchors` 边界提供：

- `GET /status`：返回状态、策略结果、revision、质量摘要和 provenance/失效原因；
- `GET /draft` 与 `PUT /draft`：读取、保存带 optimistic revision 的草稿；
- `POST /confirm`：验证并拟合，成功后保存人工确认资产；
- `GET /export`：导出兼容 CLI 的 anchors JSON。

具体路由可按仓库风格合并，但响应契约保持上述职责。状态由服务层读取确认元数据、calibration source、当前素材 provenance 和策略结果计算，不缓存为前端自维护布尔值。

备选方案是扩展 `CaptureTakeSummary` 填入全部草稿。未采用，因为列表/通用详情不应携带大量锚点；可在摘要中加入轻量 `sync_anchor_status`，详细数据仍走专用 API。

### 3. 状态与门禁分离

状态枚举表达事实：`not_required`、`required`、`draft`、`confirmed`、`auto_degraded`、`invalidated`。响应另含 `analysis_allowed` 和 `reason_codes`，由后端策略决定能否继续。

这样 `auto_degraded` 可以在不同运行策略下被允许降级分析或要求人工确认，而无需改变事实状态。前端只渲染服务端结果，不根据锚点数量、文件名或 `quality` 自行重建门禁。

初始策略保持现有运行兼容性：人工确认有效时允许；策略判定无需人工时允许；自动降级是否允许由既有 multiview execution/preflight policy 决定。对明确要求 authoritative timing 的模式，`auto_degraded` 必须阻止并要求人工标注。

### 4. provenance 指纹定义有效性

确认时保存两路以下字段的规范化快照及摘要指纹：CaptureTake id、slot、camera id、registered video id、媒体可用的稳定 identity（路径加 size/mtime 或已有内容标识）、timing sidecar path/size/mtime、timing authority、首尾 PTS、frame count。状态查询与创建分析前重新计算并比较。

registered video、camera identity 或 timing sidecar 变化会得到 `invalidated`；AnalysisJob、clip window、execution mode 和算法参数不进入指纹。该边界直接对应“会否改变 camera-local time mapping”。

备选方案是只比较 `video_id`。未采用，因为重新合并可能保持业务 id 但替换实际媒体或 sidecar。

### 5. 拟合逻辑提取为共享服务函数

把脚本中的 payload 验证、`calibrations_from_anchor_rows` 调用和 `dual_camera_sync_calibration.v1` 组装提取到服务层函数；API 和 CLI 均调用它。最小锚点数统一为 3，确认还需通过 coverage 和 residual 阈值。服务端返回字段级/规则级结构化问题，工作台将其定位到锚点覆盖、camera identity 或 residual，而不是只显示通用失败。

这避免 API 通过 subprocess 调用 CLI，也消除 CLI 与 Web 两套拟合规则漂移。

### 6. 工作台以后端草稿为权威并保留一次性迁移

工作台加载顺序为：当前素材与 timing → 服务端状态/草稿 → 若服务端无草稿且 localStorage 有旧数据，提示并执行一次性导入。后续编辑保存到服务端，localStorage 仅可作为短暂离线缓冲，不能决定确认状态。

从分析向导进入时携带显式 return context；确认成功后导航回 `/capture/takes/:id/analyze`，页面重新 GET 状态。刷新工作台或直接打开 URL 也可正常操作，不依赖内存路由状态。

### 7. 双层 preflight 防止绕过

`MultiViewAnalysisSetupPage` 使用状态 API 提前解释并门控用户流程；`create_multiview_job` 在创建 Parent/child 之前重新执行服务端同步锚点策略。若状态在页面打开后变为 invalidated，创建 API 返回结构化 preflight 问题且不创建部分任务。

## Risks / Trade-offs

- [文件组写入无法获得数据库事务的完全原子性] → 先在临时目录生成并验证整组资产，最后原子替换确认元数据；确认元数据仅引用完整 revision，孤立临时文件可清理。
- [基于 mtime 的 provenance 可能产生误失效或漏检] → 优先复用稳定媒体/sidecar identity；缺失时组合 path、size、mtime、frame count 和 PTS 范围，并在响应中暴露比较原因。
- [历史 `manual_anchors` 文件缺少 confirmation 元数据] → 提供兼容识别：校验现有 calibration 与当前 camera identity 后标记为可迁移状态，首次读取生成 confirmation 元数据；无法证明 provenance 时要求重新确认。
- [自动降级策略容易让 UI 文案与执行器门控不一致] → 状态事实与 `analysis_allowed` 分开，前端只消费后端策略结果，并共享 preflight service。
- [每次状态查询探测媒体可能有 I/O 成本] → 只读取 metadata/stat 与 timing 摘要，不扫描视频内容；必要时以 CaptureTake revision 缓存 provenance 摘要。
- [localStorage 草稿自动上传可能覆盖用户预期] → 仅在服务端无草稿时提供显式导入，使用 optimistic revision，导入成功后标记已迁移。

## Migration Plan

1. 提取共享拟合函数并保持 CLI 输出兼容，先用现有脚本测试锁定结果。
2. 增加录制级资产服务与 API；对现有 `auto_degraded` 文件只读识别，不立即批量重写。
3. 为历史 `manual_anchors` 结果增加懒迁移/兼容判定；无法验证 provenance 的结果显示需重新确认。
4. 更新工作台改用后端草稿和确认 API，保留 JSON 导出与一次性 localStorage 导入。
5. 更新分析向导状态卡和前端门禁，再启用创建任务时的服务端强制 preflight。
6. 部署后可回滚前端入口和强制门禁；新增资产为附加文件，不破坏旧执行器读取 `sync_calibration.json`。CLI 仍可恢复维护操作。

## Open Questions

- 产品默认策略中，普通 `late_fusion_v1` 是否允许 `auto_degraded` 直接继续，还是所有双摄分析都要求人工确认？设计支持两者，但实现前应将默认策略固定为配置或 execution mode 规则。
- 历史人工 calibration 无 provenance 时，是允许用户一次点击“确认沿用”，还是必须重新逐帧核对锚点？建议前者仅在原始 anchors 仍存在且 camera identity 完全匹配时开放。
