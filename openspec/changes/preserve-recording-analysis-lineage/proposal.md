## Why

单摄「录制 → 分析」链路今天会丢来源，且去重逻辑可能复用来源不可证的旧任务。两个症状都能在代码里定位到确切位置：

- **创建时丢来源**：`RecordingAnalyzePage` 走 Full 提交时只带 `videoId`，不带 `recording_session_id`；后端 `create_analysis_job` 对 `legacy_v1` 路径不做任何来源核验（`backend/app/services/mock_analysis.py:235` 起，全程没有 ownership 检查）。来源核验只存在于 `modular_v1` 的 `verified_metadata`（`backend/app/analysis_runtime/web_sources.py:75`），且它把归属冲突报成 HTTP 400（`backend/app/api/routes_analysis.py:238` 只对 `plan_preview_stale` 返回 409）。
- **内部自动分析丢来源**：`SessionService.stop_session` 在视频登记后、`SESSIONS[]` 更新与 `_persist` 之前调用 `_trigger_analysis`（`backend/app/camera/session_service.py:459`、`:835`）。该函数组装的 `AnalysisUploadMetadata` 不带 `recording_session_id`，只带 `capture_take_id` 与 `session_dir`。由于完整 metadata 会参与输入签名（`backend/app/services/job_orchestration.py:489`），这类自动任务的签名与后续同源请求**必然不同**，永远不会被复用 —— 表现为重复计算，且任务在素材历史里没有可核对的来源。
- **候选枚举不完整**：`JobStore.find_by_signature`（`backend/app/services/job_orchestration.py:729`）遍历 `self.list()` 后返回**第一条**匹配 `{queued, running, succeeded}` 的任务。`list()` 的排序键含 `updated_at`（`backend/app/services/analysis_control_plane.py` 的 `ORDER BY COALESCE(updated_at, created_at) DESC, ...`），而 `updated_at` 随状态推进变化 —— 同一批候选的顺序会随任务推进而漂移，首条命中因此不是稳定选择。
- **Modular Job 身份未隔离**：`analysis_runtime.service.submit()` 会先核验请求来源，但当前 `ArtifactStore.submit()` 仍只按 `plan_hash` 选择复用任务和 `previousJobId` 前序任务。请求核验不能替代候选 Job 的来源核验；同 `plan_hash` 的异源录制可能被折叠到同一 Job 身份。
- **Take 查询无法证明唯一**：`get_capture_take_by_source`（`backend/app/services/capture_take_service.py:127`）返回 `.first()`，无法区分「没有 Take / 唯一 Take / 多个 Take / 查询异常」。把它当成唯一 Take 使用，等于把不可核实的事实当成已核实。

本 change 只做一件事：让「录制来源」在创建、复用、历史读取三处都可核实、可追溯，并且对现有平台保持最小侵入与完整可回滚。依据 DEC-013（方案 B，授权 Propose）与 DEC-014（Q1=A / Q2=A / Q3=A，收口设计口径）。

## What Changes

- **来源核验前移到创建路径**：单摄 Full 与 Modular 共用一套服务端归属核验，覆盖 Session、登记 Video、可核实 Take；`session-only` 只在「查询成功且确认零 Take」时允许。
- **来源快照与计算签名分离**：新增任务级来源快照，作为**血缘标注**持久化在既有 Job payload 中，**不进入** `inputSignature` / `configSignature`，因此既有计算缓存身份逐字不变。
- **Legacy 与 Modular 都按来源隔离 Job 身份**：Legacy 完整枚举候选后逐个核对来源；Modular 在 `ArtifactStore.submit()` 事务内筛选同 `plan_hash` 且同源的候选。新版本的 `previousJobId` 也必须同源。来源快照不得进入 `plan_hash` 或节点计算缓存键。
- **来源身份与来源获得方式分离**：用规范化 `source_identity_equivalent()` 比较业务身份；旧 Job 缺快照时，仅接受声明完整一致且经服务端重新核验的来源。冲突、缺失或不可证明的历史来源标记为未知，不与上传来源混同。
- **Take 唯一性三态化**：把 Take 解析结果定义为 `none / unique / ambiguous / unavailable` 四态，`ambiguous` 与 `unavailable` 都不得降级为 `session-only`。
- **错误契约统一**：来源缺失、对象不存在、归属冲突和登记不可用分别映射到 400/404/409/503；显式 Take 不存在不得降级为 session-only。旧 Modular 客户端历史 400 继续按同一 machine code 兼容解析；前端不得仅凭状态码判断业务含义。
- **安全的来源状态投影**：完整 `sourceSnapshot` 保持服务端内部数据；任务摘要只提供 `verified_recording`、`upload`、`unknown` 三态 `sourceStatus`。后端录制筛选和前端 Library 归属使用同一核验结果。
- **内部自动分析可信入口**：内部自动分析使用进程内构造的可信来源上下文，绑定本次停止的 Session 与本次登记的 Video；该上下文不进入公开 HTTP Schema，不可由 `metadata`、URL 或 `session_dir` 伪造；失败不得破坏停录、登记与最终落盘。
- **单/双摄来源身份固化**：单摄允许省略 `camera_slot`，视图标识**不是**来源身份。双摄 Parent 的来源快照记录既有绑定校验确认的完整 `(video_id, slot, camera_id)` 集合；不改变绑定契约。
- **可信产物定位有明确回退顺序**：新任务只从服务端持久化关系解析 Take、Session 和产物根；不得使用 HTTP `metadata.session_dir`。所有可信位置不可用时返回既有 `location_unavailable`，不静默切换到本地目录。

不在本次范围（明确非目标）：

- 无数据库迁移、无 DDL、无索引新增；无历史 Job 批量回填；不移动或改名任何视频；不改模型与算法；不改 CI 工作流。
- 不新建 Capability，不改 `openspec/specs/` 主规格，不执行 E1/E2a/E2b/E3，不创建 PR、不部署、不 Archive。
- 不把「统一契约」当作理由，把原本可选的单摄字段变成新的必填字段。
- 不为提高复用率放宽来源匹配；宁可多建一个独立 Job，也不复用来源不可证的旧 Job。

## Capabilities

### New Capabilities

- 无。本 change 只对既有六个 Capability 追加行为，避免重复能力。

### Modified Capabilities

- `recording-analysis-bridge`：录制来源的服务端归属核验、内部自动分析的可信来源上下文、来源错误的对外呈现语义。
- `analysis-job-orchestration`：来源快照、候选完整枚举与稳定选择、幂等复用收敛为「签名等价 + 来源等价」。
- `library-analysis-start`：分析创建请求的来源契约（含单摄可省略 slot），以及创建失败的可重试语义。
- `frontend-analysis-mode-creation`：machine code 优先的错误解析，兼容历史 400 与新 409。
- `analysis-task-management`：来源不可证的历史任务保持可读、可追溯，不被改写或隐藏。
- `library-item-workspace`：素材历史按同源收拢，异源任务不得混入素材历史。
- `analysis-artifact-lineage`：新增可信产物位置解析、离线可用性及历史产物读取约束。

## Impact

- 代码（全部为提案，未实施）：
  - `backend/app/services/job_orchestration.py`：新增只读完整候选枚举；`find_by_signature` 保持签名与调用兼容，内部改为走同一枚举后取首条。
  - `backend/app/services/mock_analysis.py`、`backend/app/services/multiview_coordinator.py`：复用分支改为「枚举 → 来源等价过滤 → 稳定选择」。
  - `backend/app/analysis_runtime/service.py`、`backend/app/analysis_runtime/artifact_store.py`：Modular Job 复用与版本前序筛选同源候选，同时保持 `plan_hash` 与节点缓存身份不变。
  - 新增来源核验服务（建议 `backend/app/services/recording_source_service.py`）：Session/Video/Take 归一化与等价判定，复用 `capture_take_service` 与 `sync_anchor_service` 的既有读取路径。
  - `backend/app/camera/session_service.py`：`stop_session` 组装进程内可信来源上下文并传入创建入口；停录顺序、门控与异常恢复保持不变。
  - `backend/app/api/routes_analysis.py`：来源错误状态码映射（409 化）；错误体沿用既有 `{code, message, details}` + `redact_public_strings`。
  - `backend/app/schemas/analysis.py`、`backend/app/api/routes_analysis.py` 与 `src/services/libraryAdapter.ts`：任务摘要投影三态 `sourceStatus`，统一录制与上传素材的任务归属。
  - `src/services/analysisClient.ts`：错误对象增加结构化 `code` / `details`；创建页与素材工作区按 code 分支。
- API：不新增端点；`POST /api/analysis/jobs` 增加来源核验；任务摘要增加安全投影字段 `sourceStatus`，不公开完整 `sourceSnapshot`。
- 数据：不新增表、列、索引；来源快照（含双摄完整绑定集合）写入既有 `analysis_jobs.payload_json`。历史 Job 不回填或改写。
- 兼容：普通 Upload 仍为「无来源」合法路径；只有未显式声明 Take 且查询成功确认零 Take 时保留 `session-only`；历史来源声明可在一致且重核验通过时参与同源判定，否则状态为未知；双摄 A/B 绑定与 Parent/child 可见性不变。
- 回滚：不涉及 DDL，回滚即回退代码；已写入的来源快照对新旧代码都是未知字段（payload 读取容错），不会使旧任务不可读。
- 验证：E1、E2a 为实施期必验；E2b 由 QA Agent 在隔离本地浏览器环境执行（本 change 不执行）；E3 需负责人单独授权。
