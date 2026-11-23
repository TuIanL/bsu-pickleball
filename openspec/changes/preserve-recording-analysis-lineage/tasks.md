> 本版为 P0-01 技术评审修订版：在既有任务上补齐 Modular Job 来源隔离、历史来源归一化、请求冲突处理、来源状态投影、可信产物定位与双摄 Parent 来源身份。当前共 35 项，**均未实施、均未勾选**。

## 1. 来源对象与只读核验层

- [ ] 1.1 实现 Take 四态解析（`none` / `unique` / `ambiguous` / `unavailable`）：有界读取（`limit(2)`）判定数量，异常显式转为 `unavailable`，禁止 `.first()` 与 `except: pass`
- [ ] 1.2 实现 Session / Video / Take / Track 一致性核验：复用 `SyncAnchorAssetService._registered_inputs`（`sync_anchor_service.py:126`）读出 `slot → video_id`，`capture_tracks.video_id` 为空不计冲突
- [ ] 1.3 `[新增]` 单测：零个 / 唯一 / 多个 / 查询抛错四态各一例，并断言空 `video_id` 不构成冲突（原因：T2 要求「多候选与查询异常不得降级为 session-only」，必须由测试固定，不能靠代码审查）
- [ ] 1.4 `[新增]` 实现来源快照落盘与读取容错：写入既有 Job payload（不新增列）、冻结 `fingerprint` 的哈希输入字段顺序、旧 payload 缺字段时读为 `unknown` 而非 `none`；补指纹稳定性与旧 payload 读取单测（原因：D-01 新增字段，A-01/A-03/A-09 都断言其取值，原任务清单无对应实现项）
- [ ] 1.5 `[新增]` 实现可信产物定位解析：Take → Session → 与请求 metadata 分离的服务端 Job 产物根；只有前一层位置缺失才回退，已登记卷离线返回 `location_unavailable` 且不得切本地；忽略 HTTP `metadata.session_dir`；测试路径优先级、Worker 重启和历史 Job 原路径读取（原因：D-11 需区分可信持久化位置、客户端字段与历史兼容路径）
- [ ] 1.6 `[新增]` 归一化请求顶层与 metadata 的重复来源声明；冲突返回 409，不任选其一；仅一处声明时按契约核验；显式 `capture_take_id` 不存在返回 404 且不得降级为 session-only（原因：新请求此前没有与历史候选相同的双源冲突与 Take 缺失规则）

## 2. 服务端归属核验与错误契约

- [ ] 2.1 在 `legacy_v1` 单摄创建路径接入归属核验（当前 `mock_analysis.py:235` 起的路径完全没有 ownership 检查），`modular_v1` 保留既有 `verified_metadata`
- [ ] 2.2 实现错误码矩阵并改造 `routes_analysis.py:238` 的状态映射：400 `recording_source_required` / 404 `recording_source_not_found` / 409 `source_ownership_mismatch` / 503 `recording_source_unavailable`，响应体沿用 `{code, message, details}` 并走 `redact_public_strings`
- [ ] 2.3 单测：四类错误各一例，断言不出现 500、不泄漏绝对路径与 `session_dir`

## 3. Legacy 候选枚举与同源复用

- [ ] 3.1 新增只读方法 `JobStore.find_all_by_signature()`：一次 `list()` 扫描收全部签名匹配项，**不按状态过滤**；`find_by_signature` 改为复用它取首条
- [ ] 3.2 实现稳定比较器（`createdAt DESC, id DESC`，禁用 `updated_at`），并改造单摄（`mock_analysis.py:332`）与双摄（`multiview_coordinator.py:797`）两处复用分支为「枚举 → 来源等价 → 稳定选择 → 否则新建」；诊断日志须记录每个被跳过候选的原因（签名不等价 / 来源不符 / 状态不可复用）
- [ ] 3.3 `[新增]` 单测：首条为异源 / 无来源候选时，必须命中后续同源候选；多个同源候选按稳定顺序选择，且两次调用结果一致（原因：T1 的核心是「异源首条不得遮挡同源候选」，这是本次最重要的回归）
- [ ] 3.4 `[新增]` 单测：所有候选来源不可证 → 新建独立 Job 且不改写旧 Job；签名不等价不复用；普通 Upload 保持无来源行为（原因：Q2=A 的两种情况边界必须可区分，避免被实现成「一律新建」或「一律复用」）
- [ ] 3.5 `[新增]` 实现 `source_identity_equivalent()` 与旧 Job 来源归一化：优先读 `sourceSnapshot`；快照缺失时解析所有持久化来源声明并重新核验；`provenance`/`declaredBy` 不作为身份字段；fingerprint 只由规范化业务身份计算（原因：D-01/D-03 的旧任务兼容规则及多 provenance 等价规则此前相互冲突）
- [ ] 3.6 `[新增]` 单测：历史声明一致且重新核验成功可参与比较；顶层与 metadata 冲突、声明全缺失或 fingerprint 不一致时为 unknown 且不得复用；provenance 不同但身份相同按既定规则比较（原因：锁定旧任务复用边界并避免 unknown 被误当 Upload）
- [ ] 3.7 `[新增]` 改造 Modular `analysis_runtime.service.submit` / `ArtifactStore.submit`：在既有事务内枚举同 `plan_hash` 候选，普通复用只选择来源等价项；新版本 `previousJobId` 只从同源前序任务选择；`sourceSnapshot` 不得进入 `plan_hash` 或节点缓存键（原因：main 的 ArtifactStore 当前只按 `plan_hash` 复用及关联版本）
- [ ] 3.8 `[新增]` Modular 回归测试：同计划同源复用、同计划异源新建、同源新版本关联、异源新版本不关联、不同来源仅在既有计算输入缓存规则允许时共享产物且 Job 身份保持独立（原因：避免 Legacy 已隔离而 Modular 仍跨来源复用）

## 4. 内部自动分析可信入口

- [ ] 4.1 定义进程内 `TrustedRecordingSource`（frozen dataclass）与创建入口 keyword-only 参数 `trusted_source`，确认不出现在 `AnalysisJobCreate` 或任何 HTTP schema
- [ ] 4.2 改造 `SessionService.stop_session` / `_trigger_analysis`（`session_service.py:396`、`:835`）：构造可信上下文、补齐 metadata 的 `recording_session_id`，保持停录顺序与 `rally_context_enabled` 门控
- [ ] 4.3 `[新增]` 单测：被停止 Session 的最终快照尚未落盘时仍能创建任务；创建抛错时录制仍 completed、`auto_analysis_job_id=None`、Session 落盘与 `write_capture_metadata` 均完成（原因：T4 要求「自动分析失败不得破坏停录」，既有 `try/except` 语义必须锁死）
- [ ] 4.4 `[新增]` 单测：HTTP 请求在 `metadata` 中塞入伪造来源字段不产生内部信任；Take/Track 冲突时不创建；`rally_context_enabled` 开/关两条分支各一例（原因：DEC-014 第 4 条要求信任边界不可由 HTTP 伪造）

## 5. camera_slot 单摄/双摄语义

- [ ] 5.1 固定单摄行为：省略 `camera_slot` 合法且不补默认值；显式传入合法 slot 时按 Take 登记核对 video；非法值仍由 `Literal` 返回 422
- [ ] 5.2 双摄来源快照保存既有 `validate_binding` 核验通过的完整 `(video_id, slot, camera_id)` 集合；不改绑定逻辑，并保留 scene 标定 provenance 与 `referenceViewId` 校验
- [ ] 5.3 `[新增]` 单测：仅凭 `camera_slot="cam_1"` 无法通过来源核验（默认视图标识不得当作来源身份），并覆盖双摄 slot 与实际绑定不一致时拒绝（原因：T3 明确「默认视图标识不能替代 Recording Session / Video / Take 核验」）
- [ ] 5.4 `[新增]` 双摄 Parent 回归：同一 Take、参考机位和计划下，第二机位的登记 Video 或 `(video_id, slot, camera_id)` 集合变化时不得复用旧 Parent（原因：Parent 来源不是单一 reference Video）

## 6. 前端错误码兼容与呈现

- [ ] 6.1 扩展 `AnalysisApiError`（`src/services/analysisClient.ts:159`）增加结构化 `errorCode` / `errorDetails`，在 `parseErrorBody`（`:475`）内解析 `{code, message, details}`
- [ ] 6.2 创建页按 `code` 分支处理 HTTP 400 与 409（兼容旧 Modular 客户端历史 400），不按状态码推断业务含义，其他 400 不得被解释为来源冲突
- [ ] 6.3 任务列表与素材工作区呈现来源不可证的旧任务：一般任务列表保持可读、可追溯；不得归入任一具体录制/上传素材；隐藏来源专属控件但不隐藏任务
- [ ] 6.4 前端单测：400+code 与 409+code 同分支；普通 400 落默认分支；旧任务缺字段不抛异常
- [ ] 6.5 `[新增]` 素材历史按同源收拢：后端 Session 查询与前端 Library 使用同一规范化归属规则；录制只纳入已核实同源任务，上传只纳入明确 `upload` 且 Video 匹配任务；未知/冲突旧任务不归入任何素材（原因：后端 raw-field OR 与前端顶层优先逻辑会把冲突 Job 错归到录制）
- [ ] 6.6 `[新增]` 在公开任务摘要增加安全 `sourceStatus` 投影（`verified_recording` / `upload` / `unknown`）；仅 verified_recording 提供规范化 `recordingSessionId`，其余置空；不暴露 `sourceSnapshot`、绝对路径或可信产物根（原因：前端无法从当前摘要可靠区分无来源 Upload 与未知历史任务）
- [ ] 6.7 `[新增]` API 与前端测试：新录制/Upload/unknown 三态区分；冲突旧任务不进入任一 Session 过滤；Library 录制/上传历史与后端过滤一致；unknown 仍留在一般任务列表（原因：锁定三处归属判断使用同一契约）

## 7. 验收与证据（Apply 后执行）

- [ ] 7.1 E1 后端定向回归 + E2a 前端定向回归，记录命令、用例数与失败清单（既有 53/93 项仅为修复前基线，不作为通过证据）
- [ ] 7.2 E2b 由 QA Agent 在隔离本地浏览器执行：真实前后端服务、临时 SQLite、临时存储根、合成视频夹具；归档请求/响应原文、数据库查询结果与浏览器证据
- [ ] 7.3 负责人审阅 E2b 证据并签署结论；E3 真实录制短窗口另行申请授权，未获授权不得执行
