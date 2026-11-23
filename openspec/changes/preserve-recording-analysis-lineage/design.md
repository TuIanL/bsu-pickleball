## Context

单摄录制的分析任务在创建路径上没有来源核验，去重路径上又不能区分候选来源。两处叠加的结果是：任务要么丢失与录制的血缘，要么被复用到一个无法证明同源的旧任务上。

本轮把 DEC-014 批准的三项口径（Q1=A / Q2=A / Q3=A）与四项技术补强（T1 Legacy 完整候选枚举、T2 Take 唯一性、T3 camera_slot 单双摄语义、T4 内部可信入口）落成可实施的技术契约。以下事实均在当前工作区实测得出，不是字段名推测。

基线（`d1b74f0`，本地 `openspec/specs` 与之逐字一致）：

- 来源核验只存在于 `modular_v1`：`backend/app/analysis_runtime/web_sources.py:75` `verified_metadata`。`legacy_v1` 单摄与双摄创建路径**没有**任何归属检查。
- 归属冲突已经是既有 machine code：`web_sources.py` 三处抛 `AnalysisRuntimeError("source_ownership_mismatch", ...)`，但 `backend/app/api/routes_analysis.py:238` 把它映射成 HTTP 400（只有 `plan_preview_stale` 走 409）。
- 完整 metadata 参与输入签名：`backend/app/services/job_orchestration.py:489` `input_payload["metadata"] = payload.metadata.model_dump(...)`。因此「来源写进 metadata」等于「来源进入缓存身份」。
- 去重入口有两处：单摄 `backend/app/services/mock_analysis.py:332`，双摄 `backend/app/services/multiview_coordinator.py:797`，都调用 `find_by_signature`。
- `find_by_signature` 返回第一条匹配（`job_orchestration.py:729`），底层 `AnalysisControlPlane.list()` 的排序键含 `updated_at`（`backend/app/services/analysis_control_plane.py`），`updated_at` 随状态推进变化。
- `analysis_jobs` 只有两个索引：`(canonical_status, priority, queued_at, created_at)` 与 `(canonical_status, worker_heartbeat_at)`。**没有** `input_signature` 索引，候选枚举必然是 payload 全表扫描。
- `capture_takes` 有 `uq_take_source UNIQUE(source_session_type, source_session_id)`（`backend/app/models/capture_take.py:41`），本机 `backend/data/app.sqlite3` 的建表语句实测包含该约束；但 `_ensure_capture_storage_columns`（`backend/app/database.py:80`）只补列不补约束，`create_all` 也不会给已有表追加约束，所以**不能假定所有历史库都有它**。
- `capture_tracks.video_id` 可空（`backend/app/models/capture_track.py:72`）；本机实测 134 条 track 中 110 条 `video_id IS NULL`（82%），因此「video 冲突」只能由**非空** video_id 参与判定。
- 本地 `analysis_control.sqlite3` 实测 58 个 Job：15 个既无 `recording_session_id` 也无 `capture_take_id`（25.9%）；8 组签名各对应 2 个 Job，其中存在「同 Session 同 Take、一个 canceled 一个 succeeded」的真实配对。这直接证明「多个同源候选」不是假设。

## Goals / Non-Goals

**Goals**

1. 单摄 Full 与 Modular 创建路径共用一套可核实的来源归属核验，错误码口径统一。
2. 任务复用收敛为「计算签名等价 **且** 来源等价」；来源不可证的旧候选一律不复用。
3. Take 解析可区分零个、唯一、多个与查询失败四态，四态各有确定对外语义。
4. 内部自动分析在「最终 Session 尚未落盘」时仍能取得可信来源，且该信任不可由 HTTP 伪造。
5. 单摄 `camera_slot` 可省略的既有行为不变；双摄绑定契约不变。
6. 既有计算缓存身份（`inputSignature` / `configSignature` / `plan_hash`）逐字不变；无 DDL、无回填、可回滚。

**Non-Goals**

- 不做历史 Job 的来源回填或重写；不改写旧 payload。
- 不引入新表、新列、新索引，不合并 SQLite，不迁移文件。
- 不重写 `analysis_signature` 的构成；不引入模糊签名匹配来提高复用率。
- 不改双摄 Parent/child 可见性、机位角色、同步锚点与融合逻辑。
- 不实现预录双摄导入、媒体中心、评分、PDF、云边通信。
- 不执行 E1/E2a/E2b/E3。

## Decisions

### D-01 来源快照与计算签名分离

**决定**：新增任务级来源快照 `sourceSnapshot`，作为**血缘标注**持久化在既有 Job payload 中，**不参与** `inputSignature` / `configSignature`。

**理由**：`metadata` 已在签名内（`job_orchestration.py:489`）。若把来源写进 `metadata` 再要求「同签名、异来源」可区分，两者矛盾 —— 同签名必然同 metadata，也就必然同来源声明。要让 T1 的「首条异源、第二条同源」可构造、可测试，来源必须位于签名之外。

**形状（建议，非最终字段名）**：

```text
sourceSnapshot = {
  kind: "recording" | "upload",
  sessionId: str | None,
  videoId: str | None,
  captureTakeId: str | None,
  cameraSlot: "cam_1" | "cam_2" | None,
  viewBindings: [{videoId: str, cameraSlot: str, cameraId: str}],  # 双摄 Parent 的完整既有绑定三元组集合
  provenance: "verified_declared" | "verified_internal" | "none" | "unknown",
  declaredBy: "http_request" | "session_stop" | "none",
  sessionType: "recording" | "sync_recording" | None,
  fingerprint: str,   # 归一化后来源的稳定哈希，仅用于等价比较与日志
}
```

`provenance` 四值的含义必须区分清楚：`none` 表示**本次显式确认无来源**（普通 Upload）；`unknown` 表示历史来源不能证明，包括字段缺失、声明冲突/不完整或重新核验失败。两者 MUST NOT 合并。

**约束**：

- 只由服务端在创建时写入；从不从请求体读取。
- `provenance = "none"` 只用于本次显式确认无来源的普通 Upload；`provenance = "unknown"` 用于任何无法证明来源的历史 Job。二者 MUST NOT 互相等价。
- `fingerprint` 只由规范化业务身份字段计算，不含时间戳、路径、`provenance` 或 `declaredBy`；双摄绑定集合按稳定顺序规范化。
- 完整 `sourceSnapshot` 不属于任何 HTTP schema。任务摘要只允许暴露安全投影 `sourceStatus = verified_recording | upload | unknown`，不得暴露内部快照。
- **权威字段规则**：来源快照是唯一权威。无快照的历史 Job 不得被直接判为同源，只能以其**持久化的声明来源**参与判定，见下一条。
- **两个来源字段的关系（必须显式处理）**：任务上有两处来源声明 —— 顶层 `recordingSessionId`/`cameraSlot`，与 `metadata.recording_session_id`/`metadata.camera_slot`。二者**不是**同一事实的两种表示，历史上可能不一致：
  - 顶层字段**不进入** `inputSignature`（`input_payload` 只含 `metadata`，见 `job_orchestration.py:490-500`），而 metadata 进入。
  - 因此「签名相同、持久化来源不同」在既有数据中**真实可构造**，不是理论假设。这正是 D-02 要求全量枚举的直接原因，也是本 change 不能靠「metadata 已在签名内」推掉来源核验的原因。
  - 无快照时解析所有可用的持久化来源声明：顶层 `recordingSessionId`、`cameraSlot`、`videoId`，以及 `metadata.recording_session_id`、`capture_take_id`、`camera_slot`。同一概念在两处都有值但值不一致 → `unknown`，MUST NOT 任选其一；所有来源字段均缺失也 → `unknown`，不得推断为 Upload。
  - 旧任务至少有足以解析来源的声明、所有声明彼此一致且 L1/L2/L3 或既有多视角绑定复核成功时，才可作为临时 `verified_declared` 来源参与筛选；信息不全、登记不可访问或复核失败均 → `unknown`。
  - 新建任务时，服务端 MUST 把核验结果同时写入顶层与 `metadata`，保证二者一致。
- 读取侧容错：旧 payload 无此字段 → 视为 `unknown`，不报错（与既有「新增编排字段兼容读取」一致）。

**不改变的**：`analysis_signature` 的 `config_payload` / `input_payload` 一字不改；`plan_hash` 与节点缓存键不改。

### D-02 候选完整枚举与稳定排序（T1）

**问题**：`find_by_signature` 返回首条，且首条顺序随 `updated_at` 漂移。

**决定**：

1. 新增只读方法 `find_all_by_signature(input_signature, config_signature) -> list[AnalysisJobSummary]`，一次 `list()` 扫描收集**全部**签名匹配的 Job，**不按状态过滤**。
2. 调用方（`mock_analysis.py` / `multiview_coordinator.py`）改为：
   枚举 → 逐个判定来源等价 → 只在等价集合内按状态与不可变字段选一条 → 无合格候选则新建。
3. 排序键固定为**不可变字段**：`(createdAt DESC, id DESC)`。禁止使用 `updated_at` 作为选择依据。
4. `find_by_signature` 保留既有对外语义（仅按签名与状态匹配、返回首条），但**不再作为复用判定入口**。两条路径共用同一个枚举与同一比较器；复用与否必须由来源等价筛选决定，因此 `find_by_signature` 的返回值 MUST NOT 被直接拿去复用。

**为什么状态不参与来源判断**：来源是否可证，只取决于候选持久化的来源事实，与它成功、失败、取消还是运行中无关。若先用状态筛掉 `failed`/`canceled` 再判断来源，就会出现「因状态看不到候选」而误判为「无任何候选」的偏差。因此顺序必须是：**先按来源判定资格，再按状态判定可复用**。

**可复用状态集合**：沿用既有 `{queued, running, succeeded}`。`interrupted`、`failed`、`canceled` 保持不可复用（本机 58 个 Job 中 8 个 `interrupted`、15 个 `canceled`，沿用既有语义，不扩大）。

**查询成本与上界**：`analysis_jobs` 无签名索引，枚举成本为 O(N) payload 反序列化，与既有 `find_by_signature` 同阶（它本身也是全表 `list()`）。本机 N=58，量级无风险。**不新增索引**（属 DDL，超出本 change 范围）；若未来 N 进入 10^4 量级，另立 change 增加索引，届时语义不变。

**不做的事**：不做模糊签名匹配，不做「元数据相似」推断，不为提高复用率放宽任何来源条件。旧候选签名无法逐字等价 → 不复用（Q2）。

### D-03 来源身份等价与历史声明兼容（Q2 的正面定义）

**决定**：来源比较使用独立的 `source_identity_equivalent()`，比较规范化后的业务身份；不得把快照所有字段逐字比较，也不得把来源如何获得误当作来源是谁。

**候选侧解析顺序**（只读，不修改候选）：

1. 有 `sourceSnapshot` → 校验其身份字段及 `fingerprint` 一致后使用。
2. 无快照 → 读取 D-01 列出的顶层与 metadata 来源声明。字段缺失但仍可从其他声明唯一定位来源时，可继续重核验；重复声明冲突、全部缺失或无法唯一定位 → `unknown`。
3. 对可解析的旧声明重新验证 Session、登记 Video、Take 以及双摄绑定。只有核验成功才形成临时 `verified_declared` 来源；不得回写旧 Job。
4. `unknown` 与任何来源（包括 Upload）都不等价。没有来源快照的历史任务不因来源字段为空而被重新解释为 Upload。

**请求侧来源**：只来自请求字段冲突检查后的服务端核验结果，MUST NOT 从 `metadata.session_dir`、URL 参数或未核验客户端字段推断。

`source_identity_equivalent()` 的规范规则：

| 字段 | 比较规则 |
|---|---|
| `kind` | 必须一致；`unknown` 永不相等，`upload` 只与显式确认无来源的 `upload` 等价 |
| `sessionType`、`sessionId` | 录制来源双方都必须一致，且 Session 可重新核验 |
| 单摄 `videoId` | 必须一致，且 Video 属于该 Session 的登记集合 |
| 双摄 `viewBindings` | 规范化后 `(videoId, cameraSlot, cameraId)` 集合必须完全相等，并通过既有 `validate_binding` |
| `captureTakeId` | 必须完全相等（包括双方均为 `null`）；显式 Take 不可降级为 session-only |
| `cameraSlot` | 双方均有值时必须一致；一侧缺省时，只有登记关系能唯一证明同一 Video/slot 才可等价 |
| `provenance` | 双方都必须属于 `verified_declared` / `verified_internal`；两侧取值不必相同 |
| `declaredBy` | 仅为审计信息，不参与身份比较 |
| `fingerprint` | 必须与上述规范化业务身份字段重新计算的值一致；来源获取方式不进入哈希 |

任一身份字段无法证明、候选声明冲突或复核不可用 → 不等价。比较只读，不修正旧 metadata、不补写旧快照。

**情况 A / 情况 B 的分界**（DEC-014 Q2 原文口径）：

| 情形 | 处置 |
|---|---|
| A. 请求来源本身已通过核验，旧候选来源/签名/Take 等价无法证明 | **允许新建独立 Job**，不复用旧候选，旧 Job 原样保留 |
| B. 请求自身来源缺失、不存在、不匹配或登记不可访问 | **拒绝创建**，按 D-05 返回 400/404/409/503 |

禁止把 B 类请求用「新建一个 Job」的方式绕过验证。

### D-04 Take 唯一性四态（T2）

**问题**：`get_capture_take_by_source` 返回 `.first()`，无法区分零个、唯一、多个、异常。

**决定**：新增只读解析 `resolve_recording_take(db, session_type, session_id) -> TakeResolution`，结果为四态之一：

| 状态 | 判据 | 处置 |
|---|---|---|
| `none` | 查询成功且命中 0 条 | 允许 `session-only`（前提：Session 与 Video 已核实） |
| `unique` | 查询成功且命中恰 1 条 | 进入 Session/Video/Track 一致性核对 |
| `ambiguous` | 查询成功且命中 > 1 条 | **409 来源不唯一**，不自动选择 |
| `unavailable` | 查询抛错、连接失败、超时、存储不可访问 | **503**，可重试 |

**显式 Take ID 边界**：请求若提供 `capture_take_id`，先按 ID 查询该 Take。ID 不存在 → 404 `recording_source_not_found`；存在但归属 Session/Video/slot 不符 → 409 `source_ownership_mismatch`；查询异常 → 503 `recording_source_unavailable`。显式 ID 不得因 Session 下查询为零而降级为 `session-only`。只有请求没有显式 Take ID，且按 Session 查询成功返回 `none` 时，才允许 `session-only`。

**实现约束**：

1. 不得用 `.first()` 代替计数。用 `query(...).limit(2).all()` 一类有界读取：`len == 0` → `none`，`len == 1` → `unique`，`len == 2`（截断即足以判定）→ `ambiguous`。避免 `count(*)` 与无界读取。
2. 不依赖数据库唯一约束做判断。约束在当前 schema 存在（见 Context），但历史库可能缺失；约束是冗余保险，不是判定依据。
3. 异常必须显式捕获并转为 `unavailable`，**不得**让异常冒泡成 500，也不得吞掉后当作 `none`。禁止 `except Exception: pass`。
4. 只有 `none` 才允许 `session-only`；`ambiguous` 与 `unavailable` 一律不得降级。

**Track 与 Video 一致性**（不新增表/列）：

- 期望映射复用既有只读适配：`SyncAnchorAssetService._registered_inputs(take)`（`backend/app/services/sync_anchor_service.py:126`）从 `recording_session.json` 的 `registered_video_ids` 与 `camera_slots` 读出 `slot → video_id → camera_id`。
- 冲突判定：请求声明了 `cameraSlot` 且该 slot 的登记 video 与请求 `videoId` 不等 → 409。
- `capture_tracks.video_id` 为空表示「该轨未登记视频」，**不构成冲突**（本机 82% 的 track 即如此）；只有非空且与请求 video 不等才判冲突。
- 同一 Take 下同一 slot 出现多条非空且互不相同的 `video_id` → 409（来源不唯一）。

**不改结构**：不新增唯一索引、不改表、不做数据清理。`uq_take_source` 缺失的历史库按 `ambiguous` 逻辑处理即可，无需修复。

### D-05 错误码矩阵与 409 迁移（Q1）

**决定**：来源错误对外统一 `{code, message, details}`（沿用 `routes_analysis.py:238` 的既有信封与 `redact_public_strings` 脱敏）：

| 情况 | HTTP | code |
|---|---:|---|
| 请求声明了录制来源但缺少可解析的 Session/Video（例如只给 `capture_take_id`，既无 `recording_session_id` 也无法从 Take 推出所属会话与视频） | 400 | `recording_source_required` |
| 声明的 Session / Video / Take 在登记中不存在 | 404 | `recording_source_not_found` |
| 来源归属冲突（Session↔Video↔Take↔slot 任一不一致，或多候选 Take） | 409 | `source_ownership_mismatch` |
| 来源登记暂不可访问（DB 异常、超时、存储离线） | 503 | `recording_source_unavailable` |

**请求声明冲突**：`AnalysisJobCreate` 顶层 `recording_session_id` / `camera_slot` / `videoId` 与 `metadata` 内对应来源声明先统一解析。两处均有同一概念且值冲突 → 409 `source_ownership_mismatch`，不得挑选其中一处。只在一处声明时，按该入口的契约归一化后仍须服务端核验；两处都未声明录制来源时才走 Upload。

**HTTP 映射**：路由必须显式映射 `recording_source_required → 400`、`recording_source_not_found → 404`、`source_ownership_mismatch → 409`、`recording_source_unavailable → 503`，以及既有 `plan_preview_stale → 409`。来源查询中的已知数据库/存储异常须在来源服务转换为 `recording_source_unavailable`，不得落入通用 500 或默认 400；其他错误保留各自既有映射。

**兼容**：

- 旧 Modular 客户端读到 400 的历史行为继续可解析：前端**必须**按 `code` 判定，`status` 只作为展示信息。
- 新后端**只发 409**，不为兼容继续发 400。兼容责任在前端解析层，不在后端双发。
- `details` 必须脱敏（复用 `redact_public_strings`），不得回显绝对路径或 `session_dir`。

**对外文案**：`message` 面向用户，说明「该分析请求与录制来源不一致，请从录制页重新发起」一类可行动信息；不含内部 ID 堆栈。

### D-06 camera_slot 单摄/双摄语义（T3）

**实测事实**：

- `AnalysisUploadMetadata.camera_slot: Literal["cam_1","cam_2"] | None = None`（`backend/app/schemas/analysis.py:174`）—— **可省略，无默认值**。
- `AnalysisJobCreate.camera_slot` 同样可空（`schemas/analysis.py:268`）；`AnalysisJobSummary.cameraSlot` 也可空（`:366`）。
- `cam_1` / `cam_2` 在系统里有三种身份：`CaptureTrackSlot` 枚举（`models/capture_track.py:20`）、双摄 view id（`MultiViewViewPayload.viewId`、`JointViewInput.camera_slot`）、`SourceJobRef.cameraSlot`。**都不是**物理摄像机身份。
- 物理身份另有字段：`CaptureTrack.camera_id`、`CameraSlotConfig.camera_id`、请求侧 `cameraId`。
- 单摄轨道由 `CaptureTrackSpec(slot="cam_1", ...)` 硬编码创建（`backend/app/camera/session_service.py:297`、`:905`）—— 单摄的 `cam_1` 是**轨道创建产物**，不能反证摄像机身份。
- 既有绑定校验已经存在：`multiview_coordinator.py:101-108` 校验标定场景的 `camera_id`/`video_id`/图像尺寸与请求一致；`web_sources.py:92-104` 校验登记 slot 对应的 video 与请求 video 一致。

**决定**：

1. **单摄**：`camera_slot` 保持可选。省略时不做任何「补默认值」的写入，也不因此拒绝请求；来源核验只依赖 Session + Video（+ 可核实 Take）。默认视图标识 `cam_1` 不参与来源判定。
2. **单摄显式传入合法 slot**：允许；若该 slot 在 Take 登记中指向的 video 与请求 video 不一致 → 409。
3. **单摄传入非法值**：由既有 `Literal` 校验返回 422，不新增错误码。
4. **双摄**：创建核验完全沿用既有绑定契约（scene 标定 provenance、`referenceViewId` 必须在 views 内、`validate_binding` 的 `(video_id, slot, camera_id)` 三元组集合相等）。双摄 Parent 的来源快照必须记录该次核验的完整三元组集合；来源等价比较时集合必须完全相等。任何一路 Video、slot 或 camera_id 变化都不得只凭参考机位与 `plan_hash` 复用旧 Parent。本 change 不重写绑定契约。
5. **共享约束**：`camera_slot` 永远不是来源身份。任何实现都不得用「slot 匹配」单独证明来源；必须至少同时满足 Session 与 Video。

6. **仅带 slot 的请求**：`camera_slot` 单独出现不构成来源申报，按无来源（Upload）处理；该 slot MUST NOT 写入来源快照，也 MUST NOT 因此返回 400。

**注意（实施期约束）**：`web_sources.take_context` 要求 `len(status.provenance) == 2`（`web_sources.py:27`），即现有 Modular Take 路径**只接受双摄 Take**。单摄 Take 若走该函数会得到 `authoritative_sync_required`。本次修复不改变该函数；单摄来源核验走新的四态解析（D-04），不经过 `take_context`。这一点必须在实施时以测试固定，避免误把单摄接进双摄同步契约。

### D-07 内部自动分析可信入口（T4）

**问题**：`stop_session` 在 `_trigger_analysis` 之后才更新 `SESSIONS[]` 并 `_persist`（`session_service.py:459` 与随后的 `session = session.model_copy(...)`）。触发时刻：

- 内存 `SESSIONS[session_id]` 仍是 `status="recording"`、`video_id=None`；
- 磁盘 Session JSON 还是旧快照。

任何「重新读 Session 再核验」的实现都会在此刻失败。

**决定**：引入进程内可信来源上下文，由 `stop_session` 构造并直接传入创建入口：

```text
@dataclass(frozen=True)
class TrustedRecordingSource:
    session_id: str
    video_id: str
    capture_take_id: str | None
    camera_slot: Literal["cam_1", "cam_2"] | None
    issued_by: Literal["session_stop"]
```

**约束（逐条对应 DEC-014）**：

1. **仅由录制停止服务构造**：唯一构造点是 `SessionService.stop_session` 内部的私有方法；不在其它模块提供构造入口。
2. **与本次正在停止的 Session 绑定**：`session_id` 取自 `stop_session` 的入参对象，不取自请求、不取自 metadata。
3. **使用本次成功登记的 Video**：`video_id` 是 `video_service.register_recording(...)` 的返回值；登记失败则该分支不进入（既有 `if session.auto_analyze_after_stop and video_id` 门控不变）。
4. **冲突核验**：进入创建前仍执行 D-04 的 Take 四态核验，但 **Track/Video 比对以 `TrustedRecordingSource.video_id` 为事实源**，MUST NOT 读取尚未写盘的 `recording_session.json`。原因：`_registered_inputs` 依赖该文件（见 D-04），此刻仍是旧快照，会把本次刚登记的视频判成缺失，导致合法内部来源被 409 拒掉。仅当快照中已包含该 video 时才用 `_registered_inputs` 做交叉核对；确属冲突则**不创建**，只记内部日志，不影响停录结果。
5. **与普通请求同一归一化路径**：可信上下文只替代「来源如何获得」，之后走与 HTTP 路径相同的 `sourceSnapshot` 归一化与候选复用流程。
6. **不进公开 Schema**：`TrustedRecordingSource` 不作为 `AnalysisJobCreate` 字段存在；创建入口以 **keyword-only 参数**接收（`create_analysis_job(payload, *, trusted_source=None, db=None)`），HTTP 路由永不传该参数。
7. **不可由外部伪造**：不接受 `metadata.trusted`、URL 参数、header、`session_dir` 之类任何外部信号；`declaredBy` 只能由代码路径决定。
8. **失败不破坏停录**：`_trigger_analysis` 既有 `try/except` 保留；异常只记日志，`job_id` 保持 `None`，随后照旧构造 completed 会话、写 `auto_analysis_job_id=None`、`_persist`、`write_capture_metadata`。
9. **补齐来源字段**：`_trigger_analysis` 组装的 metadata 增加 `recording_session_id=session.session_id`（与既有 `capture_take_id`、`session_dir` 并列）。这一步的目的是让自动任务**有可核验的来源**（血缘与来源判定），MUST NOT 被解读为「提升复用率」：metadata 中的 `fileName`、`matchTitle`、`session_dir` 仍与 Web 请求不同，且整份 metadata 参与签名，因此两者签名通常仍不相等。压缩这些差异**不在**本 change 范围内。

**顺序不变**：停 FFmpeg → 登记视频 → `auto_analyze_after_stop and video_id` 门控 → `rally_context_enabled` 门控 → 触发创建 → 构造 completed 会话 → `SESSIONS[]` 与 `_persist` → `write_capture_metadata`。

### D-08 事务、并发与版本

- **事务边界**：来源核验是纯读；不写业务表。创建 Job 的写入点保持既有位置（`_JOB_STORE.create_job` / `ArtifactStore.submit`），不新增跨库事务。
- **并发**：`sourceSnapshot` 在创建时一次写入且此后不变，不做条件更新，因此不引入新竞态。控制面既有 `BEGIN IMMEDIATE` + `insert_if_missing` 语义不变。
- **Modular Job 复用**：`ArtifactStore.submit()` 在既有事务内枚举同 `plan_hash` 候选。普通提交仅可复用来源身份等价且状态为 `queued`、`running` 或 `succeeded` 的候选；先筛来源，再筛状态。不得因 `verified_metadata()` 已核验本次请求就跳过候选来源核验。
- **Modular 版本关联**：`requestNewVersion=True` 跳过 Job 复用，但设置 `previousJobId` 前仍必须筛选来源等价候选；按不可变时间与 Job ID 稳定选择同源前序任务。不存在同源前序任务时省略 `previousJobId`，不得指向异源 Job。
- **双摄 Parent 来源身份**：双摄快照记录既有 `validate_binding` 核验过的完整三元组集合；第二路登记 Video 或任何绑定成员变化时，Parent 不得复用。
- **plan_hash / 节点缓存**：`modular_v1` 的 `plan_hash` 算法、ArtifactStore 节点发布记录和既有缓存键完全不变。`sourceSnapshot`、Session/Take 身份不得加入 `plan_hash` 或计算缓存键；只有现有缓存合同判定实际输入等价时才可共享计算产物。共享计算结果不合并 Job 身份或来源血缘。
- **Status quo**：`is_runnable` 的判定、`claim_next` 的选择、worker 心跳与租约全部不改。

### D-09 存储根与历史产物

- 不改变 `StorageService` 的路径构造与 `data/outputs` 外接盘分支。
- 不调用任何会 `mkdir` 的解析函数来做只读核验；来源核验只读 `recording_session.json` / `registered_video_ids` / `capture_takes` / `capture_tracks`。
- 外接盘离线时：Take 解析返回 `unavailable`（503），**不**退化为本地路径、不写新目录。
- 历史产物根与 Job 历史按原 Job ID 可达，不做搬移。

### D-10 E2b 执行安排（Q3）

`E2b` 为**未来 Apply 之后的必验项**，本轮 Propose 不执行。正式口径：

| 项 | 要求 |
|---|---|
| 执行者 | QA Agent |
| 环境 | 隔离本地浏览器（真实前后端服务，不是 mock） |
| 数据库 | 临时 SQLite（临时路径，非 `backend/data/app.sqlite3`） |
| 存储根 | 临时存储根（非外接盘、非 `data/outputs`） |
| 素材 | 合成视频夹具（非原始比赛视频） |
| 禁止 | 不访问生产库、不修改原始视频、不使用真实生产摄像机 |
| 证据 | 请求/响应原文、数据库查询结果、浏览器操作截图或录屏，可复核 |
| 审阅 | 负责人审阅证据后才可标 E2b 通过 |

`E3` 真实录制短窗口仍需负责人单独授权，不在 Apply 自动放行范围。

### D-11 存储定位、路径与签名一致性

**问题**：`_trigger_analysis` 把 `session_dir` 放进 metadata，而整份 metadata 参与签名；本 change 又要求 HTTP 路径不信任客户端 `session_dir`。若不显式约束，会出现三处风险：① 同一业务来源因本机路径不同产生不同签名；② 内部可信上下文只活在进程内，Worker 重启后无法定位产物；③ 历史 Job 因新规则变化而无法读取。

**决定**：

1. `metadata.session_dir` 继续按原样参与既有签名；本 change MUST NOT 改写或剥离它。签名保持原规则与 sourceSnapshot 分离。
2. `session_dir` MUST NOT 作为来源判据、内部信任凭据或可信产物根。HTTP 请求里的 `metadata.session_dir` 仅为兼容字段，服务端不得用它打开、定位、创建或回退产物目录，也不得将它复制到服务端可信位置字段。
3. 新任务的可信产物定位仅来自服务端持久化关系：已登记 Take 的持久化 `storage_root` / `session_dir` → 该 Session 的持久化 `session_dir` → Job payload 中由服务端写入、与请求 metadata 分离的产物根字段。来源顺序只读、不猜路径。
4. 前一层位置**缺失**时才尝试下一层；若已登记位置存在但对应卷离线、不可读或校验失败，立即返回 `location_unavailable`，不得转用下一层本地目录伪装成功。
5. 若 Take 与 Session 均没有持久化位置，且 Job payload 中也没有可信服务端产物根，返回 `location_unavailable`；不得根据 `metadata.session_dir` 创建目录或回退。
6. 内部可信上下文 MUST NOT 承载产物定位。Worker 重启后只能从 Take、Session 或服务端写入的 Job 产物根恢复，不得依赖内存。
7. 历史 Job 读取继续使用既有历史读取路径和原有受控逻辑引用；不得将历史客户端 `metadata.session_dir` 升格为可信根。新解析规则只作用于新任务定位与来源判定，不搬移或重写历史产物。
8. `fileName`、`matchTitle`、`session_dir` 造成的同源异签名不在本 change 内处理。提高同源复用率须另立 change，不得通过放宽来源匹配抵消。

**不在本 change 内**：不做路径规范化、不重写历史 payload、不迁移任何产物目录。

### D-12 来源状态公共投影与历史归属

`sourceSnapshot` 保持服务端内部字段。为让任务列表、录制历史和上传素材区分来源状态，公开 `AnalysisJobSummary` 增加有限投影 `sourceStatus`：

| `sourceStatus` | 判定 | 对外归属 |
|---|---|---|
| `verified_recording` | 新任务有有效 recording snapshot，或旧声明完整一致且重新核验成功 | 提供规范化 `recordingSessionId`；只归入身份等价的录制 |
| `upload` | 新任务创建时服务端明确确认无录制来源 | `recordingSessionId=null`；仅可归入匹配的上传 Video |
| `unknown` | 历史快照缺失、声明冲突/不完整、重核验失败或来源登记不可用 | `recordingSessionId=null`；只留在一般任务列表，不归入录制或上传素材 |

后端 `GET /api/analysis/jobs?recording_session_id=...` 与前端 Library MUST 使用同一规范化规则；MUST NOT 用顶层或 metadata 字段的 OR 匹配，也 MUST NOT 采用“顶层优先”的客户端回退。公开摘要不得暴露完整 `sourceSnapshot`、可信存储根或绝对路径。历史任务的原始兼容字段可以保留，但来源归属只以该投影及规范化身份为准。

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| 来源判定过严导致复用率下降，重复计算增多 | 算力与等待时间上升（单摄 CPU 推理慢） | 这是 Q2 的**有意选择**：宁可多建，也不复用不可证任务。补齐来源字段只改善可追溯性；metadata 中其他签名字段仍可能让同源请求产生不同签名，本 change 不承诺提升复用率 |
| `sourceSnapshot` 不进签名 → 同签名异来源共存 | 状态集合内出现多条等价候选 | D-02 的稳定排序 + D-03 逐字段等价把选择变成确定函数 |
| 全文枚举为 O(N) payload 扫描 | N 大时创建变慢 | 与既有 `find_by_signature` 同阶，本机 N=58；不新增索引（DDL 超范围），留作后续独立 change |
| 历史库缺 `uq_take_source` | 可能出现同源多 Take | D-04 四态显式判定，`ambiguous` → 409，不依赖约束 |
| 单摄 Take 无法进入 `take_context`（要求 2 路 provenance） | 误接会导致 `authoritative_sync_required` | D-06 明确单摄走新的四态解析；以测试固定 |
| 409 化改变既有客户端行为 | 旧客户端可能把 409 当未知错误 | 前端按 `code` 判定；`analysisClient` 增加结构化 code（`src/services/analysisClient.ts:159`、`:475`） |
| 内部可信上下文被误用为「绕过校验后门」 | 信任边界失守 | 构造点唯一、keyword-only 参数、不进 schema、不可由 metadata 伪造（D-07 第 1/6/7 条） |

## Migration Plan

1. **无迁移**。不新增表/列/索引，不改 SQLite schema，不移动文件。
2. 部署顺序建议（Apply 阶段）：先上后端（来源核验 + 409 + 快照写入），再上前端（code 解析）。后端先行时旧前端会把 409 显示为通用错误，但不会误判成功 —— 这是可接受的降级。
3. 回滚：回退代码即可。已写入 payload 的 `sourceSnapshot` 对回退后的代码是未知字段，`_model()` 解析容错（与既有「新增编排字段兼容读取」一致），旧任务不受影响。
4. 历史 Job：不改写、不回填、不删除。来源快照或 provenance 缺失等价于 `unknown`，不得等同于显式 Upload 的 `none`；一致且可重新核验的旧声明可临时参与来源筛选，不可证明的仍不可复用。

## Open Questions

- 无阻塞性未决项。以下为实现期需在 apply 时以测试固定的细节，不影响本轮 Propose 收口：
  - 来源核验服务的具体模块落点与函数命名（建议 `backend/app/services/recording_source_service.py`）。
  - `sourceSnapshot.fingerprint` 的哈希输入字段顺序（需在实现时冻结并写测试，避免后续无意变更）。
  - 前端 `sourceStatus` 的 UI 文案与无障碍标签；API enum 值已固定，展示文案不改变三态语义。
